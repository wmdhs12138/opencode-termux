#!/usr/bin/env python3

import pathlib
import struct
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from elf_native import ElfInfo
from graph_format import Graph, TRAILER


def synthetic_graph():
    name = b"/$bunfs/root/libopentui-test.so"
    contents = b"\x7fELFold-asset"
    data = bytearray(name + contents)
    modules_at = len(data)
    record = bytearray(52)
    struct.pack_into("<II", record, 0, 0, len(name))
    struct.pack_into("<II", record, 8, len(name), len(contents))
    data.extend(record)
    offsets_at = len(data)
    data.extend(struct.pack("<QIIIIII", offsets_at, modules_at, 52, 0, 0, 0, 0))
    data.extend(TRAILER)
    return bytes(data), contents


class GraphTests(unittest.TestCase):
    def test_append_and_repoint_preserves_old_graph_data(self):
        payload, old = synthetic_graph()
        graph = Graph(payload)
        replacement = b"\x7fELFnew-bionic-asset-that-is-larger"
        report = graph.replace_contents_by_append(0, replacement)
        self.assertEqual(graph.module(0).contents, replacement)
        self.assertIn(old, graph.data)
        self.assertEqual(graph.byte_count, graph.offsets_at)
        self.assertTrue(graph.data.endswith(TRAILER))
        self.assertEqual(report["strategy"] if "strategy" in report else "append", "append")

    def test_module_metadata(self):
        graph = Graph(synthetic_graph()[0])
        module = graph.module(0)
        self.assertEqual(module.index, 0)
        self.assertEqual(module.display_name, "/$bunfs/root/libopentui-test.so")
        self.assertEqual(graph.module_count, 1)


class ElfPolicyTests(unittest.TestCase):
    def test_glibc_sonames_are_rejected(self):
        info = ElfInfo(
            machine=0xB7,
            interpreter="/lib/ld-linux-aarch64.so.1",
            needed=("libc.so.6", "libgcc_s.so.1", "libutil.so.1"),
        )
        self.assertEqual(
            info.glibc_dependencies,
            (
                "/lib/ld-linux-aarch64.so.1",
                "libc.so.6",
                "libgcc_s.so.1",
                "libutil.so.1",
            ),
        )

    def test_bionic_sonames_pass(self):
        info = ElfInfo(
            machine=0xB7,
            interpreter=None,
            needed=("libc.so", "libm.so", "libdl.so"),
        )
        self.assertEqual(info.glibc_dependencies, ())
        self.assertEqual(info.unbundled_dependencies, ())

    def test_shared_cxx_runtime_requires_bundling(self):
        info = ElfInfo(
            machine=0xB7,
            interpreter=None,
            needed=("libc.so", "libc++_shared.so"),
        )
        self.assertEqual(info.glibc_dependencies, ())
        self.assertEqual(info.unbundled_dependencies, ("libc++_shared.so",))


if __name__ == "__main__":
    unittest.main()
