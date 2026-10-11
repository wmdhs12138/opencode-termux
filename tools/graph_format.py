#!/usr/bin/env python3
"""Read Bun >= 1.4 standalone module graphs.

The graph payload does not include the leading u64 length stored in an ELF.
Pointers in module records are relative to the beginning of this payload.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct


TRAILER = b"\n---- Bun! ----\n"
OFFSETS_SIZE = 32
STRIDE = 52


class GraphError(ValueError):
    pass


@dataclass(frozen=True)
class Module:
    index: int
    record_offset: int
    name: bytes
    contents: bytes
    contents_offset: int
    contents_length: int

    @property
    def display_name(self) -> str:
        return self.name.decode("utf-8", "replace")


class Graph:
    def __init__(self, data: bytes | bytearray):
        self.data = bytearray(data)
        self._parse()

    @classmethod
    def from_path(cls, path: str) -> "Graph":
        with open(path, "rb") as stream:
            return cls(stream.read())

    def _parse(self) -> None:
        if not self.data.endswith(TRAILER):
            raise GraphError("graph trailer is missing")
        self.offsets_at = len(self.data) - OFFSETS_SIZE - len(TRAILER)
        if self.offsets_at < 0:
            raise GraphError("graph is too small")
        (
            self.byte_count,
            self.modules_at,
            self.modules_len,
            self.entry,
            self.argv_at,
            self.argv_len,
            self.flags,
        ) = struct.unpack_from("<QIIIIII", self.data, self.offsets_at)
        if self.byte_count != self.offsets_at:
            raise GraphError(
                f"byte_count {self.byte_count} != Offsets position {self.offsets_at}"
            )
        if not self.modules_len or self.modules_len % STRIDE:
            raise GraphError(f"unsupported module table length {self.modules_len}")
        if self.modules_at + self.modules_len > self.offsets_at:
            raise GraphError("module table overlaps the Offsets structure")
        self.module_count = self.modules_len // STRIDE
        if self.entry >= self.module_count:
            raise GraphError(
                f"entry point {self.entry} is outside {self.module_count} modules"
            )
        for module in self.modules():
            if module.contents_offset + module.contents_length > self.offsets_at:
                raise GraphError(f"module {module.index} contents run past graph data")

    def pointer(self, at: int) -> tuple[int, int]:
        offset, length = struct.unpack_from("<II", self.data, at)
        if length and offset + length > self.offsets_at:
            raise GraphError(
                f"StringPointer at {at} points outside graph: {offset}+{length}"
            )
        return offset, length

    def module(self, index: int) -> Module:
        if index < 0 or index >= self.module_count:
            raise IndexError(index)
        record = self.modules_at + index * STRIDE
        name_at, name_len = self.pointer(record)
        contents_at, contents_len = self.pointer(record + 8)
        return Module(
            index=index,
            record_offset=record,
            name=bytes(self.data[name_at : name_at + name_len]),
            contents=bytes(self.data[contents_at : contents_at + contents_len]),
            contents_offset=contents_at,
            contents_length=contents_len,
        )

    def modules(self):
        for index in range(self.module_count):
            yield self.module(index)
