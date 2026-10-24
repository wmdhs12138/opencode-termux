# Native asset ledger

编译前替换进 `node_modules` 的 Bionic 资产（`tools/swap_native_assets.py`）：

| npm 包里的文件 | 上游 | `DT_NEEDED` |
|---|---:|---|
| `@opentui/core-linux-arm64/libopentui.so` | OpenTUI 0.6.8 | `libm.so`, `libc.so`, `libdl.so` |
| `@ff-labs/fff-bin-linux-arm64-gnu/libfff_c.so` | FFF 0.10.5 | `libz.so`, `libdl.so`, `libm.so`, `libc.so` |
| `@parcel/watcher-linux-arm64-glibc/watcher.node` | `@parcel/watcher` 2.5.1 | `liblog.so`, `libdl.so`, `libm.so`, `libc.so` |
| `bun-pty/rust-pty/target/release/librust_pty_arm64.so` | `bun-pty` 0.4.11 | `libdl.so`, `libc.so` |
| `bun-pty/rust-pty/target/release/librust_pty_arm64_musl.so` | 同上，同一个文件 | `libdl.so`, `libc.so` |

bun-pty 0.4.10 起在 Linux 上同时内嵌 musl 版，只在 ld-musl 下加载。它只依赖 `libc.so`，
与 Android 的同名，`--require-bionic` 审计分不出来，所以同样换成 Bionic 库。

npm 包的版本必须与表中一致（即 `versions.json`），否则构建失败。产物里的模块名带
Bun 生成的哈希后缀，如 `libopentui-x8k2b6xk.so`。

原生输出可能包含构建目录或 build-id，因此每次构建的实际 SHA-256 由
`dist/build-manifest.json` 记录，不把它误当作源码身份。源码归档哈希固定在
`versions.json`。

## FFF pointer boundary

Bionic 的 tagged heap pointer 可能大于 JavaScript 的安全整数上限。FFF 的 Bun wrapper
使用 `read.ptr()` 并以 `number` 做地址运算，实例创建后执行文件搜索会丢失地址位并崩溃
（`Segmentation fault at address 0x7FFFFFFFFFFFFFFF`），销毁实例时也一样。
`patches/fff-bun-android.patch` 在编译前修补 `@ff-labs/fff-bun`：指针字段改用
`read.u64()`，地址以 `bigint` 保存，数组步进也使用 `BigInt`；目录和混合搜索不再逐项
调用返回 number 的 getter，而是从结果结构体读取数组基址。

Bun 解析这个包时走 `exports` 的 `bun` 条件，打包的是 `src/ffi.ts` 而不是
`dist/index.js`，补丁两处都改。文件、目录和混合搜索已在真机上通过；发布验收由
`tools/serve_smoke.py` 在 git 仓库里经 `opencode serve` 再测一次打包后的 wrapper，非
仓库目录 OpenCode 用 ripgrep，测不到 FFF。

## Watcher

`@parcel/watcher-android-arm64@2.5.1` 的预编译文件依赖 `libc++_shared.so`，在 Android
linker namespace 下不能作为独立单文件可靠加载。本项目从相同官方源码重建并静态链接
C++ runtime；监听功能 smoke 已通过。

## PTY

v1.18.32 内嵌的 FFI PTY 来自 `bun-pty` 0.4.8。其 `portable-pty` 0.8.1 不支持 Android，
项目更新到兼容的 0.9.0 后交叉编译，真实 PTY 输出与退出码 smoke 已通过。

Rust 原生资产链接 `native/tls-align.S`，确保 Android AArch64 动态链接器可接受的 TLS
alignment。OpenTUI 构建同样注入该 alignment anchor。
