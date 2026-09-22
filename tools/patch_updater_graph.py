#!/usr/bin/env python3
"""Route OpenCode's bundled updater through Bionic-verified Termux releases."""

from __future__ import annotations

import argparse
import json

from graph_format import Graph, GraphError


UPSTREAM_INSTALLER = "https://opencode.ai/install"
TERMUX_INSTALLER = (
    "https://raw.githubusercontent.com/wmdhs12138/opencode-termux/main/install.sh"
)
UPSTREAM_RELEASES = "https://api.github.com/repos/anomalyco/opencode/releases/latest"
TERMUX_RELEASES = "https://api.github.com/repos/wmdhs12138/opencode-termux/releases/latest"
METHOD_BEFORE = 'if(process.execPath.includes(R.join(".opencode","bin")))return"curl";'
METHOD_AFTER = (
    'if(process.execPath.startsWith((process.env.PREFIX??'
    '"/data/data/com.termux/files/usr")+"/bin/")||'
    'process.execPath.includes(R.join(".opencode","bin")))return"curl";'
)


def replace_exact(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise GraphError(
            f"updater pattern count mismatch: expected 1, got {count}: {old!r}"
        )
    return text.replace(old, new)


def patch_updater(source: bytes) -> bytes:
    text = source.decode("utf-8")
    text = replace_exact(text, UPSTREAM_INSTALLER, TERMUX_INSTALLER)
    text = replace_exact(text, UPSTREAM_RELEASES, TERMUX_RELEASES)
    text = replace_exact(text, METHOD_BEFORE, METHOD_AFTER)
    return text.encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--report")
    args = parser.parse_args()

    graph = Graph.from_path(args.input)
    matches = [
        module
        for module in graph.modules()
        if UPSTREAM_INSTALLER.encode() in module.contents
        and UPSTREAM_RELEASES.encode() in module.contents
    ]
    if len(matches) != 1:
        raise GraphError(f"expected one bundled updater module, found {len(matches)}")

    target = matches[0]
    result = graph.replace_contents_by_append(
        target.index, patch_updater(target.contents)
    )
    result["patch"] = "termux-bionic-updater"
    graph.write(args.output)

    encoded = json.dumps(result, indent=2) + "\n"
    if args.report:
        with open(args.report, "w", encoding="utf-8") as stream:
            stream.write(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
