# Architecture

## 从源码编译

上游发布 Linux 版的方式是：在 Linux 主机上执行 `packages/opencode/script/build.ts`，
由 `bun build --compile` 把 bundle 嵌进目标平台的 Bun。本项目走同一条路，只换掉被嵌入的
Bun：

```text
OpenCode vX.Y.Z（tag 对应的提交）
   │ patches/opencode-*.patch（fuzz 0）
   │ bun install
   │ tools/swap_native_assets.py：Bionic 原生组件替换 node_modules 里的 glibc 版
   │ bun build --compile --target bun-linux-arm64，executablePath = Android Bun
   ▼
dist/opencode = 官方 bun-linux-aarch64-android + OpenCode bundle
```

编译主机是 glibc AArch64 Linux，用与底座同版本的官方 Bun（`versions.json` 的
`host_bun` 与 `base_bun`）。两者版本必须一致，因为 bundle 的格式由编译用的 Bun 决定。

## 为什么不在 Termux 里编译

`bun build --compile` 在打包时把 `process.platform` 和 `process.arch` 写死成常量。
Android 版 Bun 写进去的是 `android`，而 OpenTUI（`$8[platform]`）、FFF（`fff-bin-linux-*`）
和 `@parcel/watcher`（`watcher-${platform}-${arch}`）都按平台名挑原生包，只认
`linux`。glibc 主机上的 Bun 写的是 `linux`，和上游发布的二进制完全一致；运行时 Android
Bun 照常执行这些已经写死的分支。

## Android 补丁

| 补丁 | 改什么 |
| --- | --- |
| `opencode-0001-compile-on-android-bun` | `build.ts` 从 `OPENCODE_TERMUX_BUN` 取被嵌入的 Bun；主机跑不了 Android 产物，跳过主机上的 `--version` 冒烟 |
| `opencode-0002-update-from-termux-releases` | `$PREFIX/bin` 识别为 curl 安装；最新版和安装脚本改为本项目的 Release；新增只读的 `update`；`update` 和 `upgrade` 按二进制哈希判断（`src/installation/termux.ts`） |
| `fff-bun-android` | FFF 的 Bun wrapper 用 `read.u64` 读指针并以 bigint 运算：Android AArch64 的堆指针高字节带 tag，JavaScript number 存不下 |
| `opentui-android`、`bun-pty-android` | 原生组件本身的 Android 构建，见 [native-assets.md](native-assets.md) |

OpenCode 的补丁按 fuzz 0 应用；上游改了相关代码时构建直接失败，不会悄悄打偏。

## 原生组件

`bun install` 在 glibc 主机上装的是 linux-arm64 的平台包。`swap_native_assets.py` 在编译前
把这四个文件换成 Termux 里从源码编译的 Bionic 版本：

| npm 包 | 文件 |
| --- | --- |
| `@opentui/core-linux-arm64` | `libopentui.so` |
| `@parcel/watcher-linux-arm64-glibc` | `watcher.node` |
| `@ff-labs/fff-bin-linux-arm64-gnu` | `libfff_c.so` |
| `bun-pty` | `rust-pty/target/release/librust_pty_arm64.so` |

装上的版本必须等于 `versions.json` 锁定、原生组件实际编译的版本，否则失败：上游升级依赖时
要先更新组件。替换是删掉再写新文件，因为 Bun 把 `node_modules` 硬链接到全局缓存。

编译后仍从产物里提取模块图，用 `audit_native_assets.py --require-bionic` 审计：任何一个
内嵌 ELF 带 glibc 依赖都不会进入发布。

## 发布门禁

正式产物必须同时满足：

1. 补丁全部按 fuzz 0 应用，原生组件版本与 `versions.json` 一致；
2. 产物模块图里的内嵌 ELF 都是 AArch64 Bionic；
3. `--version` 与源码 tag 一致；
4. `update` 命令能运行；
5. `debug file search` 经由打过补丁的 FFF wrapper 找到文件；
6. TUI 在隔离 HOME 中渲染真实帧；
7. 原生组件各自的 FFF / watcher / PTY 冒烟通过（在组件编译时）。

1、2 在编译主机上检查（`scripts/compile.sh`），3 到 6 在 termux-docker 里运行
（`scripts/verify.sh`）。只有全部通过，候选文件才会成为 `dist/opencode`。
