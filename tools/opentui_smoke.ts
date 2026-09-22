import { dlopen, FFIType } from "bun:ffi";

const library = process.argv[2];
if (!library) throw new Error("usage: opentui_smoke.ts LIBOPENTUI");

const handle = dlopen(library, {
  YGFloatIsUndefined: { args: [FFIType.f32], returns: FFIType.bool },
});
const result = handle.symbols.YGFloatIsUndefined(Number.NaN);
handle.close();
if (!result) throw new Error("OpenTUI/Yoga FFI call returned false for NaN");
console.log(JSON.stringify({ dlopen: true, ffi: true }));
