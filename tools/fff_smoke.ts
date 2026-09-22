import { CString, dlopen, FFIType, ptr, read, type Pointer } from "bun:ffi";

const libraryPath = process.argv[2];
const basePath = process.argv[3] ?? process.cwd();
if (!libraryPath) throw new Error("usage: fff_smoke.ts LIBFFF [BASE_PATH]");

const lib = dlopen(libraryPath, {
  fff_create_instance_with: { args: [FFIType.ptr], returns: FFIType.ptr },
  fff_wait_for_scan: { args: [FFIType.ptr, FFIType.u64], returns: FFIType.ptr },
  fff_search: {
    args: [FFIType.ptr, FFIType.cstring, FFIType.cstring, FFIType.u32,
      FFIType.u32, FFIType.u32, FFIType.i32, FFIType.u32],
    returns: FFIType.ptr,
  },
  fff_free_result: { args: [FFIType.ptr], returns: FFIType.void },
  fff_free_search_result: { args: [FFIType.ptr], returns: FFIType.void },
  fff_destroy: { args: [FFIType.ptr], returns: FFIType.void },
});

const asPtr = (value: bigint) => value as unknown as Pointer;
const cstring = (value: string) => Buffer.from(value + "\0");
const writePointer = (buffer: Buffer, offset: number, value: Buffer | null) =>
  buffer.writeBigUInt64LE(value ? BigInt(ptr(value) as unknown as number) : 0n, offset);

function unwrap(result: Pointer | null): { handle: bigint; intValue: bigint } {
  if (result === null) throw new Error("FFF returned a null result pointer");
  const ok = read.u8(result, 0) !== 0;
  const error = read.u64(result, 8);
  const handle = read.u64(result, 16);
  const intValue = read.i64(result, 24);
  if (!ok) {
    const message = error === 0n ? "unknown FFF error" : new CString(asPtr(error)).toString();
    lib.symbols.fff_free_result(result);
    throw new Error(message);
  }
  lib.symbols.fff_free_result(result);
  return { handle, intValue };
}

const base = cstring(basePath);
const options = Buffer.alloc(88);
options.writeUInt32LE(1, 0);
writePointer(options, 8, base);
options.writeUInt8(1, 32); // mmap cache
options.writeUInt8(0, 33); // content indexing
options.writeUInt8(0, 34); // watcher

const created = unwrap(lib.symbols.fff_create_instance_with(ptr(options)));
if (created.handle === 0n) throw new Error("FFF returned a null instance handle");

try {
  const waited = unwrap(lib.symbols.fff_wait_for_scan(asPtr(created.handle), 10_000n));
  if (waited.intValue === 0n) throw new Error("FFF scan timed out");

  const query = cstring("README");
  const current = cstring("");
  const searched = unwrap(lib.symbols.fff_search(
    asPtr(created.handle), ptr(query), ptr(current), 0, 0, 10, 0, 0,
  ));
  if (searched.handle === 0n) throw new Error("FFF returned a null search result");
  const searchPtr = asPtr(searched.handle);
  const count = read.u32(searchPtr, 16);
  const totalMatched = read.u32(searchPtr, 20);
  lib.symbols.fff_free_search_result(searchPtr);
  if (totalMatched < 1 || count < 1) throw new Error("FFF README search returned no results");
  console.log(JSON.stringify({ create: true, scan: true, search: true, count, totalMatched }));
} finally {
  lib.symbols.fff_destroy(asPtr(created.handle));
}
