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

同一 OpenCode 版本因构建工具链更新（例如 Bun 底座）重新发布时，tag 是 `vX.Y.Z-rN`。`update` 和 `upgrade` 按二进制哈希判断，
能识别这种重新发布；v1.18.35 及更早版本自带的 `upgrade` 只比较版本号，需要重新运行一次安装命令。

## 实现

官方程序位于 Bun standalone 的模块图中。构建流程提取该 graph，替换其中的 OpenTUI、FFF、`@parcel/watcher` 和 `bun-pty` 原生组件，再将它嫁接到固定版本的 Bionic Bun。

```text
official opencode-linux-arm64
             │ extract / patch Bun graph
             ▼
     replace native components
             │ strict ELF audit
             ▼
        pinned Bionic Bun
             │ graph graft
             ▼
          dist/opencode
```

补丁使用精确、版本受控的匹配；上游结构或原生 ABI 变化时，构建会直接失败而不是产出未经验证的文件。当前验证基线为 OpenCode v1.18.35。

## CI

GitHub Actions 在 ARM64 runner 的官方 Termux Docker 环境中完成 Bionic 构建：

- PR：运行工具、安装器、发布流程与 graph 回归测试；
- 推送至 `main`：完整构建与验收；最新版还没有 Release 时自动发布；
- 每天：检查官方最新版，通过全部测试后自动发布；
- 手动运行：构建指定版本；勾选 `recut` 在工具链变化后重新发布同一版本（`vX.Y.Z-rN`）。

发布前会验证源码哈希、graph 结构、原生 ELF 依赖、版本输出及真实 TUI 启动。详见 [CI 文档](docs/ci.md)、[原生组件说明](docs/native-assets.md) 和 [维护手册](docs/maintaining.md)。

## 从源码构建

```bash
make fetch VERSION=1.18.32
make fetch-bun
make build-native
make build-strict
```

Termux 侧需要 `clang`、`proot-distro`、`ndk-multilib`、`ndk-multilib-native-static`、`curl`、`patch` 和 Python。Rust/Zig 的 Android 交叉编译环境使用 `android-build` proot 容器。

第三方组件及许可见 [THIRD_PARTY.md](THIRD_PARTY.md)。
