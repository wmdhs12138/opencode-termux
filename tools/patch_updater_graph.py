#!/usr/bin/env python3
"""Route OpenCode's bundled updater through Bionic-verified Termux releases.

Upstream ships minified JS, so identifiers such as the upgrade command
variable or the UI/log helpers are renamed on every release. They are read
from the bundled upgrade command itself instead of being hard-coded.

A release is either vX.Y.Z or a re-cut vX.Y.Z-rN of the same OpenCode version
(new toolchain, same upstream code). The version alone cannot tell them apart,
so the explicit commands compare the running binary's SHA-256 with the latest
release's build-manifest.json:

  opencode update   reports a newer version, or a rebuilt one of this version
  opencode upgrade  no longer skips the installed version when the latest
                    release of it is a different build

`Installation.latest()`, and with it the TUI's automatic update check, keeps
comparing versions, so a re-cut never triggers a background reinstall.
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
    rf'if\((?P<version>{ID})===(?P<target>{ID})\)\{{(?P=log)\.warn\(`opencode upgrade skipped: '
    rf'.*?(?P<outro>{ID})\("Done"\);return\}}',
    re.DOTALL,
)
# Injected in front of the upgrade command, so every name it uses is in scope.
# TermuxBuildCheck hashes process.execPath with Bun's native SHA-256 (about a
# second for the ~200 MB binary) and reads the latest release's manifest.
UPDATE_COMMAND = (
    'var TermuxBuildCheck=async()=>{{let termuxResponse=await fetch("{releases}");'
    'if(!termuxResponse.ok)throw Error(`HTTP ${{termuxResponse.status}} from the release manifest`);'
    'let termuxManifest=await termuxResponse.json(),termuxHash=new Bun.CryptoHasher("sha256");'
    'for await(let termuxChunk of Bun.file(process.execPath).stream())termuxHash.update(termuxChunk);'
    'return{{version:String(termuxManifest.tag_name??"").replace(/^v/,""),'
    'build:String(termuxManifest.output_sha256??""),current:termuxHash.digest("hex")}}}},'
    'TermuxSameBuild=async(termuxVersion)=>{{try{{let termuxBuild=await TermuxBuildCheck();'
    'return termuxBuild.version!==termuxVersion||!termuxBuild.build||'
    'termuxBuild.build===termuxBuild.current}}catch{{return true}}}},'
    'TermuxUpdateCommand={{command:"update",describe:"check for opencode updates",'
    'handler:async()=>{{{ui}.empty(),{ui}.println({ui}.logo("  ")),{ui}.empty(),'
    '{intro}("Update");let termuxBuild=await TermuxBuildCheck().catch(termuxError=>'
    'termuxError instanceof Error?termuxError:Error(String(termuxError)));'
    'if(termuxBuild instanceof Error){{{log}.error(`Update check failed: ${{termuxBuild.message}}`),'
    '{outro}("Done");return}}'
    '{log}.info(`Current: ${{{version}}} (build ${{termuxBuild.current.slice(0,12)}})`),'
    '{log}.info(`Latest: ${{termuxBuild.version}} (build ${{termuxBuild.build.slice(0,12)}})`),'
    '{version}!==termuxBuild.version?{log}.warn(`Update available: ${{termuxBuild.version}}. '
    'Run opencode upgrade to install it.`):'
    'termuxBuild.build&&termuxBuild.build!==termuxBuild.current?'
    '{log}.warn(`A rebuilt OpenCode ${{termuxBuild.version}} is available. '
    'Run opencode upgrade to install it.`):'
    '{log}.info("OpenCode is up to date"),{outro}("Done")}}}};'
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
        + UPDATE_COMMAND.format(releases=TERMUX_RELEASES, **names)
        + text[command.start() :]
    )
    skip = (
        f"if({names['version']}==={names['target']}){{"
        f"{names['log']}.warn(`opencode upgrade skipped: "
    )
    text = replace_exact(
        text,
        skip,
        skip.replace(
            "){",
            f"&&await TermuxSameBuild({names['target']})){{",
            1,
        ),
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
        "upgrade_compares_builds": True,
    }
    graph.write(args.output)

    encoded = json.dumps(result, indent=2) + "\n"
    if args.report:
        with open(args.report, "w", encoding="utf-8") as stream:
            stream.write(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
