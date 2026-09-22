#!/usr/bin/env python3
"""Replace one embedded ELF asset by appending a new graph payload."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys

from elf_native import ElfError, inspect_elf
from graph_format import Graph, GraphError


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("graph")
    parser.add_argument("replacement")
    parser.add_argument("output")
    parser.add_argument(
        "--name-regex", default=r"(?:^|/)libopentui(?:-[^/]*)?\.so$"
    )
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        graph = Graph.from_path(args.graph)
        with open(args.replacement, "rb") as stream:
            replacement = stream.read()
        info = inspect_elf(replacement)
        if not info.is_aarch64:
            raise GraphError("replacement is not AArch64")
        if info.glibc_dependencies:
            raise GraphError(
                "replacement has glibc dependencies: "
                + ", ".join(info.glibc_dependencies)
            )
        if info.unbundled_dependencies:
            raise GraphError(
                "replacement has unbundled dependencies: "
                + ", ".join(info.unbundled_dependencies)
            )
        pattern = re.compile(args.name_regex)
        matches = [
            module
            for module in graph.modules()
            if module.contents.startswith(b"\x7fELF")
            and pattern.search(module.display_name)
        ]
        if len(matches) != 1:
            names = ", ".join(item.display_name for item in matches) or "none"
            raise GraphError(
                f"expected exactly one matching ELF asset, found {len(matches)}: {names}"
            )
        old_sha = hashlib.sha256(matches[0].contents).hexdigest()
        report = graph.replace_contents_by_append(matches[0].index, replacement)
        report.update(
            {
                "old_sha256": old_sha,
                "new_sha256": hashlib.sha256(replacement).hexdigest(),
                "new_needed": list(info.needed),
                "strategy": "append-and-repoint",
            }
        )
        graph.write(args.output)
    except (OSError, GraphError, ElfError, re.error) as exc:
        print(f"replace-native-asset: {exc}", file=sys.stderr)
        return 1
    encoded = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.report:
        with open(args.report, "w", encoding="utf-8") as stream:
            stream.write(encoded)
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
