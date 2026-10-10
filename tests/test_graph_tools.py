#!/usr/bin/env python3

import pathlib
import struct
import subprocess
import sys
import tempfile
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


class GraftTests(unittest.TestCase):
    """tools/revive_patch.py on a minimal ELF shaped like an android Bun base."""

    BUN_SLOT = 0x100
    SEG_END = 0x200     # file end of the writable PT_LOAD
    BSS_END = 0x8000
    SYMTAB = b"\xaa" * 64

    def base_elf(self):
        # One RW PT_LOAD [0, SEG_END) with .bss up to BSS_END. The base keeps
        # non-loaded data (.shstrtab, .symtab, section headers) right after
        # SEG_END, inside the .bss range, as the official Bun 1.4.3 does.
        names = b"\0.bun\0.shstrtab\0.symtab\0"
        shstrtab_off = self.SEG_END
        symtab_off = shstrtab_off + len(names)
        shoff = (symtab_off + len(self.SYMTAB) + 7) & ~7
        out = bytearray(shoff + 4 * 64)
        out[:16] = b"\x7fELF\x02\x01\x01" + b"\0" * 9
        struct.pack_into("<HHIQQQIHHHHHH", out, 16, 3, 183, 1, 0, 64, shoff,
                         0, 64, 56, 1, 64, 4, 2)
        struct.pack_into("<IIQQQQQQ", out, 64, 1, 6, 0, 0, 0,
                         self.SEG_END, self.BSS_END, 0x10000)
        out[0x110:0x11a] = b"Bun v1.4.3"
        out[shstrtab_off:shstrtab_off + len(names)] = names
        out[symtab_off:symtab_off + len(self.SYMTAB)] = self.SYMTAB
        for i, (name, kind, flags, addr, off, size) in enumerate([
            (0, 0, 0, 0, 0, 0),
            (1, 1, 3, self.BUN_SLOT, self.BUN_SLOT, 8),
            (6, 3, 0, 0, shstrtab_off, len(names)),
            (16, 2, 0, 0, symtab_off, len(self.SYMTAB)),
        ]):
            struct.pack_into("<IIQQQQIIQQ", out, shoff + i * 64,
                             name, kind, flags, addr, off, size, 0, 0, 8, 0)
        return bytes(out)

    def graft(self, base):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "bun").write_bytes(base)
            (root / "graph.bin").write_bytes(b"/$bunfs/root/x.js" + b"\0" * 32 + TRAILER)
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "revive_patch.py"),
                 "--bun", str(root / "bun"), "--graph", str(root / "graph.bin"),
                 "--out", str(root / "out")],
                text=True, capture_output=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            return (root / "out").read_bytes()

    def test_old_bss_extent_maps_as_zeros(self):
        out = self.graft(self.base_elf())
        payload = struct.unpack_from("<Q", out, self.BUN_SLOT)[0]
        self.assertGreaterEqual(payload, self.BSS_END)
        self.assertEqual(out[self.SEG_END:payload], bytes(payload - self.SEG_END))

    def test_native_assets_come_back_out_of_a_grafted_binary(self):
        assets = {
            "/$bunfs/root/libopentui-a1.so": b"opentui",
            "/$bunfs/root/libfff_c-b2.so": b"fff",
            "/$bunfs/root/watcher-c3.node": b"watcher",
            "/$bunfs/root/librust_pty_arm64-d4.so": b"pty",
            "/$bunfs/root/index.js": b"js",
        }
        data, records = bytearray(), bytearray()
        for name, contents in assets.items():
            record = bytearray(52)
            struct.pack_into("<II", record, 0, len(data), len(name))
            struct.pack_into("<II", record, 8, len(data) + len(name), len(contents))
            data.extend(name.encode() + contents)
            records.extend(record)
        modules_at = len(data)
        data.extend(records)
        data.extend(struct.pack("<QIIIIII", len(data), modules_at, len(records), 0, 0, 0, 0))
        data.extend(TRAILER)
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "bun").write_bytes(self.base_elf())
            (root / "graph.bin").write_bytes(data)
            tools = ROOT / "tools"
            subprocess.run([sys.executable, str(tools / "revive_patch.py"), "--bun", str(root / "bun"),
                            "--graph", str(root / "graph.bin"), "--out", str(root / "opencode")],
                           check=True, capture_output=True)
            proc = subprocess.run([sys.executable, str(tools / "dump_native_assets.py"),
                                   str(root / "opencode"), str(root / "out")],
                                  text=True, capture_output=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            found = dict(line.split("=", 1) for line in proc.stdout.split())
            self.assertEqual(sorted(found), ["FFF_SO", "OPENTUI_SO", "RUST_PTY_SO", "WATCHER_NODE"])
            self.assertEqual(pathlib.Path(found["OPENTUI_SO"]).read_bytes(), b"opentui")
            self.assertEqual(pathlib.Path(found["WATCHER_NODE"]).name, "watcher-c3.node")

    def test_section_headers_survive_outside_the_mapped_range(self):
        out = self.graft(self.base_elf())
        filesz = struct.unpack_from("<Q", out, 64 + 32)[0]
        shoff, = struct.unpack_from("<Q", out, 0x28)
        self.assertGreaterEqual(shoff, filesz)
        sections = {}
        for i in range(4):
            name, _, _, addr, off, size = struct.unpack_from(
                "<IIQQQQ", out, shoff + i * 64)
            sections[name] = (addr, off, size)
        names_off = sections[6][1]
        self.assertEqual(out[names_off:names_off + 5], b"\0.bun")
        self.assertEqual(sections[1][:2], (self.BUN_SLOT, self.BUN_SLOT))
        _, symtab_off, size = sections[16]
        self.assertGreaterEqual(symtab_off, filesz)
        self.assertEqual(out[symtab_off:symtab_off + size], self.SYMTAB)


if __name__ == "__main__":
    unittest.main()
