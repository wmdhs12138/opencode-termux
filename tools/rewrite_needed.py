#!/usr/bin/env python3
"""Rewrite a DT_NEEDED string in-place without growing the ELF string table."""

from __future__ import annotations

import argparse
from pathlib import Path

from elf_native import inspect_elf


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("old")
    parser.add_argument("new")
    args = parser.parse_args()

    if len(args.new.encode()) > len(args.old.encode()):
        parser.error("replacement must not be longer than the original SONAME")
    data = bytearray(Path(args.input).read_bytes())
    before = inspect_elf(data)
    if args.old not in before.needed:
        parser.error(f"{args.old!r} is not a DT_NEEDED entry")
    needle = args.old.encode() + b"\0"
    matches = [index for index in range(len(data)) if data.startswith(needle, index)]
    if len(matches) != 1:
        parser.error(f"expected one string-table match for {args.old!r}, found {len(matches)}")
    replacement = args.new.encode().ljust(len(args.old), b"\0") + b"\0"
    data[matches[0] : matches[0] + len(needle)] = replacement
    after = inspect_elf(data)
    expected = tuple(args.new if item == args.old else item for item in before.needed)
    if after.needed != expected:
        parser.error("rewritten ELF did not produce the expected DT_NEEDED table")
    Path(args.output).write_bytes(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
