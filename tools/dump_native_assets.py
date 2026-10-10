#!/usr/bin/env python3
"""Pull the Bionic native assets back out of a released opencode binary.

The assets are built with the NDK, Rust and Zig, which a phone rarely has. To
try a new Bun base or a graph patch on a device, reuse the ones a release
already carries:

  python3 tools/dump_native_assets.py opencode work/native-from-release

prints shell assignments for scripts/build.sh (OPENTUI_SO=..., FFF_SO=...,
WATCHER_NODE=..., RUST_PTY_SO=...). See docs/maintaining.md.
"""

from __future__ import annotations

import argparse
import re
import struct
from pathlib import Path

from graph_format import Graph, TRAILER

ASSETS = {
    "OPENTUI_SO": re.compile(r"(?:^|/)libopentui(?:-[^/]*)?\.so$"),
    "FFF_SO": re.compile(r"(?:^|/)libfff_c(?:-[^/]*)?\.so$"),
    "WATCHER_NODE": re.compile(r"(?:^|/)watcher-[^/]*\.node$"),
    "RUST_PTY_SO": re.compile(r"(?:^|/)librust_pty_arm64-[^/]*\.so$"),
}


def grafted_graph(data: bytes) -> bytes:
    """The module graph of a plain-offset grafted ELF (tools/revive_patch.py)."""
    shoff = struct.unpack_from("<Q", data, 0x28)[0]
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", data, 0x3A)
    headers = [struct.unpack_from("<IIQQQQ", data, shoff + i * shentsize) for i in range(shnum)]
    names = headers[shstrndx][4]
    slot = next(
        (h[4] for h in headers if data[names + h[0]:].split(b"\0", 1)[0] == b".bun"), None
    )
    if slot is None:
        raise SystemExit("no .bun section: not a grafted opencode binary")
    payload = struct.unpack_from("<Q", data, slot)[0]
    length = struct.unpack_from("<Q", data, payload)[0]
    graph = data[payload + 8 : payload + 8 + length]
    if not graph.endswith(TRAILER):
        raise SystemExit("the .bun slot does not point at a module graph")
    return graph


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("binary")
    parser.add_argument("out_dir")
    args = parser.parse_args()

    graph = Graph(grafted_graph(Path(args.binary).read_bytes()))
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    found = {}
    for module in graph.modules():
        for var, pattern in ASSETS.items():
            if pattern.search(module.display_name):
                if var in found:
                    raise SystemExit(f"more than one {var} in the graph")
                path = out / module.display_name.rsplit("/", 1)[-1]
                path.write_bytes(module.contents)
                found[var] = path.resolve()
    missing = sorted(set(ASSETS) - set(found))
    if missing:
        raise SystemExit(f"missing from the graph: {', '.join(missing)}")
    for var in ASSETS:
        print(f"{var}={found[var]}")


if __name__ == "__main__":
    main()
