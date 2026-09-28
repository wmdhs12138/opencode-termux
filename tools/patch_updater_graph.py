#!/usr/bin/env python3
"""Route OpenCode's bundled updater through Bionic-verified Termux releases.

Upstream ships minified JS, so identifiers such as the upgrade command
variable or the UI/log helpers are renamed on every release. They are read
from the bundled upgrade command itself instead of being hard-coded.
"""

from __future__ import annotations

import argparse
import json
import re

from graph_format import Graph, GraphError


UPSTREAM_INSTALLER = "https://opencode.ai/install"
TERMUX_INSTALLER = (
    "https://raw.githubusercontent.com/wmdhs12138/opencode-termux/main/install.sh"
)
UPSTREAM_RELEASES = "https://api.github.com/repos/anomalyco/opencode/releases/latest"
TERMUX_RELEASES = (
    "https://github.com/wmdhs12138/opencode-termux/releases/latest/download/"
    "build-manifest.json"
)
ID = r"[A-Za-z_$][\w$]*"
METHOD_PATTERN = re.compile(
    rf'if\(process\.execPath\.includes\((?P<path>{ID})\.join\("\.opencode","bin"\)\)\)'
    r'return"curl";'
)
METHOD_AFTER = (
    'if(process.execPath.startsWith((process.env.PREFIX??'
    '"/data/data/com.termux/files/usr")+"/bin/")||'
    'process.execPath.includes({path}.join(".opencode","bin")))return"curl";'
)
COMMAND_MARKER = 'command:"upgrade [target]",describe:'
# Anchors on the upgrade handler's own calls, so every captured name is
# guaranteed to be in scope where the update command is injected.
COMMAND_PATTERN = re.compile(
    rf'var (?P<command>{ID})=\{{command:"upgrade \[target\]",describe:'
    rf'.*?handler:async\({ID}\)=>\{{'
    rf'(?P<ui>{ID})\.empty\(\),(?P=ui)\.println\((?P=ui)\.logo\("  "\)\),(?P=ui)\.empty\(\),'
    rf'(?P<intro>{ID})\("Upgrade"\);'
    rf'let {ID}=await (?P<installation>{ID})\.method\(\)'
    rf'.*?(?P<log>{ID})\.info\("Using method: "'
    rf'.*?await (?P=installation)\.latest\(\);'
    rf'if\((?P<version>{ID})==={ID}\)\{{(?P=log)\.warn\(`opencode upgrade skipped: '
    rf'.*?(?P<outro>{ID})\("Done"\);return\}}',
    re.DOTALL,
)
UPDATE_COMMAND = (
    'var TermuxUpdateCommand={{command:"update",describe:"check for opencode updates",'
    'handler:async()=>{{{ui}.empty(),{ui}.println({ui}.logo("  ")),{ui}.empty(),'
    '{intro}("Update");let termuxLatest=await {installation}.latest()'
    '.catch(termuxError=>termuxError);if(typeof termuxLatest!=="string"){{'
    '{log}.error(`Update check failed: ${{termuxLatest instanceof Error?'
    'termuxLatest.message:String(termuxLatest)}}`),{outro}("Done");return}}'
    '{log}.info(`Current: ${{{version}}}`),{log}.info(`Latest: ${{termuxLatest}}`),'
    '{version}===termuxLatest?{log}.info("OpenCode is up to date"):'
    '{log}.warn(`Update available: ${{termuxLatest}}. '
    'Run opencode upgrade to install it.`),{outro}("Done")}}}};'
)


def replace_exact(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise GraphError(
            f"updater pattern count mismatch: expected 1, got {count}: {old!r}"
        )
    return text.replace(old, new)


def match_one(pattern: re.Pattern[str], text: str, label: str) -> re.Match[str]:
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise GraphError(
            f"updater {label} match mismatch: expected 1, got {len(matches)}"
        )
    return matches[0]


def patch_updater(source: bytes) -> bytes:
    text = source.decode("utf-8")
    text = replace_exact(text, UPSTREAM_INSTALLER, TERMUX_INSTALLER)
    text = replace_exact(text, UPSTREAM_RELEASES, TERMUX_RELEASES)
    method = match_one(METHOD_PATTERN, text, "install method")
    text = (
        text[: method.start()]
        + METHOD_AFTER.format(path=method["path"])
        + text[method.end() :]
    )
    return text.encode("utf-8")


def patch_command(source: bytes) -> bytes:
    text = source.decode("utf-8")
    command = match_one(COMMAND_PATTERN, text, "upgrade command")
    names = command.groupdict()
    text = (
        text[: command.start()]
        + UPDATE_COMMAND.format(**names)
        + text[command.start() :]
    )
    text = replace_exact(
        text,
        f".command({names['command']})",
        f".command(TermuxUpdateCommand).command({names['command']})",
    )
    return text.encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--report")
    args = parser.parse_args()

    graph = Graph.from_path(args.input)
    service_matches = [
        module
        for module in graph.modules()
        if UPSTREAM_INSTALLER.encode() in module.contents
        and UPSTREAM_RELEASES.encode() in module.contents
    ]
    if len(service_matches) != 1:
        raise GraphError(
            f"expected one bundled updater module, found {len(service_matches)}"
        )

    service = service_matches[0]
    service_result = graph.replace_contents_by_append(
        service.index, patch_updater(service.contents)
    )
    command_matches = [
        module
        for module in graph.modules()
        if COMMAND_MARKER.encode() in module.contents
    ]
    if len(command_matches) != 1:
        raise GraphError(
            f"expected one bundled upgrade command, found {len(command_matches)}"
        )
    command = command_matches[0]
    command_result = graph.replace_contents_by_append(
        command.index, patch_command(command.contents)
    )
    result = {
        "patch": "termux-bionic-updater",
        "modules": [service_result, command_result],
        "update_check_command": True,
    }
    graph.write(args.output)

    encoded = json.dumps(result, indent=2) + "\n"
    if args.report:
        with open(args.report, "w", encoding="utf-8") as stream:
            stream.write(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
