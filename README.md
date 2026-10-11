# opencode-termux

让官方 [OpenCode](https://github.com/anomalyco/opencode) 在 Termux 原生运行。

本项目将 Linux AArch64 standalone 中的 glibc 原生组件替换为 Bionic 版本，最终产物可由 Android linker 直接加载，无需 glibc、proot 或其他兼容层。

[![build](https://github.com/wmdhs12138/opencode-termux/actions/workflows/build.yml/badge.svg)](https://github.com/wmdhs12138/opencode-termux/actions/workflows/build.yml)
[![release](https://img.shields.io/github/v/release/wmdhs12138/opencode-termux?display_name=tag&sort=semver)](https://github.com/wmdhs12138/opencode-termux/releases/latest)

## 安装

要求：AArch64、Android 9（API 28）或更高版本。

```bash
curl -fsSL https://raw.githubusercontent.com/wmdhs12138/opencode-termux/main/install.sh | bash
```

安装器会下载最新 Release、校验 SHA-256，并安装到 `$PREFIX/bin/opencode`；已装的就是这个构建时不重复下载。

安装指定版本：

```bash
curl -fsSL https://raw.githubusercontent.com/wmdhs12138/opencode-termux/main/install.sh | VERSION=1.18.32 bash
```

`VERSION=X.Y.Z` 安装该版本最新的一次构建，`VERSION=X.Y.Z-rN` 安装指定的那一次。

也可以从 [GitHub Releases](https://github.com/wmdhs12138/opencode-termux/releases) 手动下载。

## 更新

```bash
opencode update   # 检查是否有新版本
opencode upgrade  # 下载并安装新版本
```

两个命令均使用本项目经过 Bionic CI 验证的 Release，不会下载官方 glibc 版本。重复运行安装命令也可以完成更新。

OpenCode 2 还没有 Termux 版本：`opencode upgrade --major` 和 TUI 里的 OpenCode 2 升级在本构建中不可用（上游的升级会安装官方 glibc 版，在 Termux 上无法运行）。

同一 OpenCode 版本因构建工具链更新（例如 Bun 底座）重新发布时，tag 是 `vX.Y.Z-rN`。`update` 和 `upgrade` 按二进制哈希判断，
能识别这种重新发布；v1.18.35 及更早版本自带的 `upgrade` 只比较版本号，需要重新运行一次安装命令。

## 实现

从 OpenCode 的 release tag 源码编译，方式与上游发布 Linux 版相同：在 glibc AArch64 主机上执行上游的 `script/build.ts`；区别是可执行文件嵌入的是官方 Android 版 Bun，而不是 glibc 版。

```text
OpenCode vX.Y.Z 源码
        │ Android 补丁（patches/opencode-*.patch）
        │ bun install
        │ 换入在 Termux 里从源码编译的 Bionic 原生组件
        ▼
bun build --compile（glibc 主机，嵌入官方 Android Bun）
        │ 在 Termux 里运行验收
        ▼
   dist/opencode
```

编译不能放在 Termux 里做：Android 版 Bun 打包时把 `process.platform` 定为 `android`，OpenTUI、FFF 和 `@parcel/watcher` 都不认这个平台。详见 [架构说明](docs/architecture.md)。

补丁按 fuzz 0 应用，原生组件的版本与 `versions.json` 逐一核对；上游代码或依赖变化时，构建会直接失败而不是产出未经验证的文件。

## CI

GitHub Actions 在 ARM64 runner 上完成构建，Bionic 部分都在官方 Termux Docker 环境里：

- PR：运行工具、安装器、发布流程与补丁工具的回归测试；
- 推送至 `main`：完整构建与验收；最新版还没有 Release 时自动发布；
- 每天：检查官方最新版，通过全部测试后自动发布；
- 手动运行：构建指定版本；勾选 `recut` 在工具链变化后重新发布同一版本（`vX.Y.Z-rN`）。

一次构建分三步：Termux 里编译原生组件，runner 上从源码编译 OpenCode，再回到 Termux 里运行验收（`--version`、`update`、文件搜索和真实 TUI 启动）。详见 [CI 文档](docs/ci.md)、[原生组件说明](docs/native-assets.md) 和 [维护手册](docs/maintaining.md)。

## 从源码构建

推荐直接用 CI。本地要分两种环境：

```bash
# Termux：原生组件
make build-native

# glibc AArch64 Linux（ARM64 服务器，或 proot-distro 里的 Ubuntu），同一个仓库目录
make fetch-source VERSION=1.18.35
make compile

# Termux：验收，通过后得到 dist/opencode
make verify
```

Termux 侧需要 `clang`、`proot-distro`、`ndk-multilib`、`ndk-multilib-native-static`、`curl`、`patch` 和 Python，Rust/Zig 的 Android 交叉编译使用 proot 里的 Ubuntu。编译 OpenCode 的一侧需要 Node.js 22+、Python、`patch` 和 C/C++ 编译器（上游依赖的安装脚本会用到 node-gyp）。

第三方组件及许可见 [THIRD_PARTY.md](THIRD_PARTY.md)。
