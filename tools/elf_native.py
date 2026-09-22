#!/usr/bin/env python3
"""Small dependency reader for embedded little-endian ELF64 assets."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import struct
import sys


PT_LOAD = 1
PT_DYNAMIC = 2
PT_INTERP = 3
DT_NULL = 0
DT_NEEDED = 1
DT_STRTAB = 5

# Libraries from Android's public native platform surface that the port may
# resolve without shipping an extra shared object. Keep this deliberately
# narrow; a new dependency must be reviewed instead of silently passing.
ANDROID_SYSTEM_LIBRARIES = frozenset(
    {
        "libandroid.so",
        "libc.so",
        "libdl.so",
        "liblog.so",
        "libm.so",
        "libz.so",
    }
)


class ElfError(ValueError):
    pass


@dataclass(frozen=True)
class ElfInfo:
    machine: int
    interpreter: str | None
    needed: tuple[str, ...]

    @property
    def is_aarch64(self) -> bool:
        return self.machine == 0xB7

    @property
    def glibc_dependencies(self) -> tuple[str, ...]:
        bad = []
        if self.interpreter and "ld-linux" in self.interpreter:
            bad.append(self.interpreter)
        for name in self.needed:
            if name in {
                "libc.so.6",
                "libm.so.6",
                "libstdc++.so.6",
                "libgcc_s.so.1",
                "libpthread.so.0",
                "libdl.so.2",
                "librt.so.1",
                "libutil.so.1",
            }:
                bad.append(name)
        return tuple(bad)

    @property
    def unbundled_dependencies(self) -> tuple[str, ...]:
        """Dependencies not supplied by Android's reviewed system allowlist."""
        return tuple(name for name in self.needed if name not in ANDROID_SYSTEM_LIBRARIES)


def _cstring(data: bytes, offset: int) -> str:
    if offset < 0 or offset >= len(data):
        raise ElfError(f"string offset {offset} is outside ELF")
    end = data.find(b"\0", offset)
    if end < 0:
        raise ElfError("unterminated ELF string")
    return data[offset:end].decode("utf-8", "replace")


def inspect_elf(data: bytes) -> ElfInfo:
    if len(data) < 64 or data[:4] != b"\x7fELF":
        raise ElfError("not an ELF")
    if data[4] != 2 or data[5] != 1:
        raise ElfError("only little-endian ELF64 is supported")
    machine = struct.unpack_from("<H", data, 18)[0]
    phoff = struct.unpack_from("<Q", data, 32)[0]
    phentsize = struct.unpack_from("<H", data, 54)[0]
    phnum = struct.unpack_from("<H", data, 56)[0]
    if phentsize < 56 or phoff + phentsize * phnum > len(data):
        raise ElfError("invalid program header table")

    headers = []
    for index in range(phnum):
        at = phoff + index * phentsize
        typ, flags = struct.unpack_from("<II", data, at)
        offset, vaddr, _paddr, filesz, memsz, align = struct.unpack_from(
            "<QQQQQQ", data, at + 8
        )
        if offset + filesz > len(data):
            raise ElfError(f"program header {index} runs past ELF")
        headers.append((typ, flags, offset, vaddr, filesz, memsz, align))

    def vaddr_to_offset(address: int) -> int:
        for typ, _flags, offset, vaddr, filesz, _memsz, _align in headers:
            if typ == PT_LOAD and vaddr <= address < vaddr + filesz:
                return offset + address - vaddr
        raise ElfError(f"virtual address {address:#x} is not file-backed")

    interpreter = None
    dynamic = None
    for typ, _flags, offset, _vaddr, filesz, _memsz, _align in headers:
        if typ == PT_INTERP:
            interpreter = data[offset : offset + filesz].rstrip(b"\0").decode(
                "utf-8", "replace"
            )
        elif typ == PT_DYNAMIC:
            dynamic = (offset, filesz)

    needed_offsets = []
    strtab_address = None
    if dynamic:
        offset, size = dynamic
        for at in range(offset, offset + size, 16):
            tag, value = struct.unpack_from("<qQ", data, at)
            if tag == DT_NULL:
                break
            if tag == DT_NEEDED:
                needed_offsets.append(value)
            elif tag == DT_STRTAB:
                strtab_address = value
    needed = []
    if needed_offsets:
        if strtab_address is None:
            raise ElfError("DT_NEEDED exists without DT_STRTAB")
        strtab = vaddr_to_offset(strtab_address)
        needed = [_cstring(data, strtab + item) for item in needed_offsets]
    return ElfInfo(machine=machine, interpreter=interpreter, needed=tuple(needed))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("elf")
    args = parser.parse_args()
    try:
        with open(args.elf, "rb") as stream:
            info = inspect_elf(stream.read())
    except (OSError, ElfError) as exc:
        print(f"elf-native: {exc}", file=sys.stderr)
        return 2
    report = {
        "machine": info.machine,
        "aarch64": info.is_aarch64,
        "interpreter": info.interpreter,
        "needed": list(info.needed),
        "glibc_dependencies": list(info.glibc_dependencies),
        "unbundled_dependencies": list(info.unbundled_dependencies),
    }
    print(json.dumps(report, indent=2))
    return 0 if info.is_aarch64 and not info.glibc_dependencies and not info.unbundled_dependencies else 1


if __name__ == "__main__":
    raise SystemExit(main())
