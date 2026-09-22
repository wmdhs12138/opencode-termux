# Native asset ledger

官方 OpenCode v1.18.32 输入 SHA-256：
`7c6e67883fcb230b7d4cb1bfea821756ed8b320c1fb44e9c36c8e7fc8725826b`。

严格构建中的 Bionic 替换资产：

| Graph 资产 | 上游 | `DT_NEEDED` |
|---|---:|---|
| `libopentui-*.so` | OpenTUI 0.4.5 | `libm.so`, `libc.so`, `libdl.so` |
| `libfff_c-*.so` | FFF 0.9.4 | `libz.so`, `libdl.so`, `libm.so`, `libc.so` |
| `watcher-*.node` | `@parcel/watcher` 2.5.1 | `liblog.so`, `libdl.so`, `libm.so`, `libc.so` |
| `librust_pty_arm64-*.so` | `bun-pty` 0.4.8 | `libdl.so`, `libc.so` |

原生输出可能包含构建目录或 build-id，因此每次构建的实际 SHA-256 由
`dist/build-manifest.json` 记录，不把它误当作源码身份。源码归档哈希固定在
`versions.json`。

## FFF pointer boundary

Bionic 的 tagged heap pointer 可能大于 JavaScript 的安全整数上限。FFF 0.9.4 的 Bun
wrapper 使用 `read.ptr()` 并以 `number` 做地址运算，实例创建后执行文件搜索会丢失地址
位并崩溃。项目对 OpenCode graph 中的 minified wrapper 做版本受控修补：指针字段改用
`read.u64()`，地址以 `bigint` 保存，数组步进也使用 `BigInt`。实际的创建、扫描、
搜索、结果读取与销毁 smoke 已通过。

## Watcher

`@parcel/watcher-android-arm64@2.5.1` 的预编译文件依赖 `libc++_shared.so`，在 Android
linker namespace 下不能作为独立单文件可靠加载。本项目从相同官方源码重建并静态链接
C++ runtime；监听功能 smoke 已通过。

## PTY

v1.18.32 内嵌的 FFI PTY 来自 `bun-pty` 0.4.8。其 `portable-pty` 0.8.1 不支持 Android，
项目更新到兼容的 0.9.0 后交叉编译，真实 PTY 输出与退出码 smoke 已通过。

Rust 原生资产链接 `native/tls-align.S`，确保 Android AArch64 动态链接器可接受的 TLS
alignment。OpenTUI 构建同样注入该 alignment anchor。
