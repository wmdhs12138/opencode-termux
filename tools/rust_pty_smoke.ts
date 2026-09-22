import { dlopen, FFIType, ptr } from "bun:ffi";
import { Buffer } from "node:buffer";

const path = process.argv[2];
if (!path) throw new Error("usage: bun rust_pty_smoke.ts LIBRARY");

const lib = dlopen(path, {
  bun_pty_spawn: {
    args: [FFIType.cstring, FFIType.cstring, FFIType.cstring, FFIType.i32, FFIType.i32],
    returns: FFIType.i32,
  },
  bun_pty_read: {
    args: [FFIType.i32, FFIType.pointer, FFIType.i32],
    returns: FFIType.i32,
  },
  bun_pty_get_exit_code: { args: [FFIType.i32], returns: FFIType.i32 },
  bun_pty_close: { args: [FFIType.i32], returns: FFIType.void },
});

const expected = "termux-rust-pty-smoke";
const command = "'/system/bin/sh' '-c' 'printf termux-rust-pty-smoke'\0";
const handle = lib.symbols.bun_pty_spawn(
  Buffer.from(command),
  Buffer.from(`${process.cwd()}\0`),
  Buffer.from("\0"),
  80,
  24,
);
if (handle <= 0) throw new Error(`PTY spawn failed: ${handle}`);

const buffer = Buffer.alloc(4096);
let output = "";
let exitCode = -1;
const deadline = Date.now() + 5000;
try {
  while (Date.now() < deadline) {
    const size = lib.symbols.bun_pty_read(handle, ptr(buffer), buffer.length);
    if (size > 0) output += buffer.subarray(0, size).toString("utf8");
    if (size === -2) {
      exitCode = lib.symbols.bun_pty_get_exit_code(handle);
      break;
    }
    if (size < 0) throw new Error(`PTY read failed: ${size}`);
    await Bun.sleep(8);
  }
} finally {
  lib.symbols.bun_pty_close(handle);
}

if (!output.includes(expected) || exitCode !== 0) {
  throw new Error(`PTY smoke failed: output=${JSON.stringify(output)} exit=${exitCode}`);
}
console.log(JSON.stringify({ output: output.trim(), exitCode }));
