# opencode-termux

把官方 [`anomalyco/opencode`](https://github.com/anomalyco/opencode) 的 Linux
AArch64 standalone 移植到 Android/Bionic AArch64。目标是单 ELF 直接运行，且不依赖
glibc、proot 或兼容层。

[![build](https://github.com/wmdhs12138/opencode-termux/actions/workflows/build.yml/badge.svg)](https://github.com/wmdhs12138/opencode-termux/actions/workflows/build.yml)
[![release](https://img.shields.io/github/v/release/wmdhs12138/opencode-termux?display_name=tag&sort=semver)](https://github.com/wmdhs12138/opencode-termux/releases/latest)

## 当前基线

首个完整验证基线是官方 OpenCode **v1.18.32**。输入来自官方 GitHub Release 的
`opencode-linux-arm64.tar.gz`。CI 会
跟踪官方 Latest；上游原生 ABI 变化时构建会安全失败，待版本锁和补丁更新后再发布。

已完成一次严格构建：

- 官方输入 SHA-256：`7c6e67883fcb230b7d4cb1bfea821756ed8b320c1fb44e9c36c8e7fc8725826b`
- 输出能由 `/system/bin/linker64` 直接加载；
- `opencode --version` 返回 `1.18.32`；
- 1318 个 Bun graph 模块已解析并重新嫁接；
- 四个内嵌原生资产全部替换为 AArch64/Bionic 版本；
- 严格 ELF 审计、graph 闭环验证和真实 TUI smoke 均通过。

四个官方 v1.18.32 原生依赖是：

| 资产 | 上游版本 | Termux 处理 |
|---|---:|---|
| OpenTUI | 0.4.5 | 官方源码交叉编译为 Bionic |
| FFF | 0.9.4 | 官方源码交叉编译；修复 Android tagged pointer 精度 |
| `@parcel/watcher` | 2.5.1 | 官方源码交叉编译并静态链接 C++ runtime |
| `bun-pty` | 0.4.8 | 官方源码交叉编译；更新 Android 可用的 `portable-pty` |

`opencode-pty` 属于后续版本的实验，不在 v1.18.32 的默认构建和发布链中。

## 原理

官方 Linux ARM64 文件本身是 glibc ELF，但 OpenCode 程序位于 Bun standalone 的模块图
中。本项目提取该 graph，替换其中的 glibc 原生库，再把 graph 嫁接到固定的 Bionic Bun
底座。FFF 的 JavaScript FFI wrapper 也会经过精确、版本受控的改写，因为 Android
AArch64 malloc 指针可能使用 top-byte tag，不能安全存入 JavaScript `number`。

```text
official opencode-linux-arm64
            │ extract Bun graph
            ▼
  patch FFF pointer handling
            │
            ├─ OpenTUI 0.4.5 (Bionic)
            ├─ FFF 0.9.4 (Bionic)
            ├─ watcher 2.5.1 (Bionic)
            └─ bun-pty 0.4.8 (Bionic)
            │ strict native audit
            ▼
      pinned Bionic Bun
            │ graph graft
            ▼
       dist/opencode
```

## 安装 / 更新

在 Termux 中运行一条命令：

```bash
curl -fsSL https://raw.githubusercontent.com/wmdhs12138/opencode-termux/main/install.sh | bash
```

重复运行就是更新。安装器会自动获取最新版、验证 SHA-256，并安装到
`$PREFIX/bin/opencode`。只支持 AArch64 和 Android API 28+。

OpenCode 自带的升级命令也已适配 Termux：

```bash
opencode upgrade
```

它只会查询并安装本项目已经通过 Bionic CI 验证的 Release，不会下载官方 glibc 包。

安装指定版本：

```bash
curl -fsSL https://raw.githubusercontent.com/wmdhs12138/opencode-termux/main/install.sh | VERSION=1.18.32 bash
```

也可以继续从 [GitHub Releases](https://github.com/wmdhs12138/opencode-termux/releases)
手动下载 zip 安装。

## 从源码构建

```bash
make fetch VERSION=1.18.32
make fetch-bun
make build-native
make build-strict
```

仅审计官方输入：

```bash
make audit
```

验证已有产物：

```bash
make verify
make smoke
```

Termux 侧需要 `clang`、`proot-distro`、`ndk-multilib`、
`ndk-multilib-native-static`、`curl`、`patch` 和 Python。Rust/Zig 的 Android
交叉编译环境使用 `android-build` proot 容器。

## CI 自动构建

GitHub Actions 使用原生 `ubuntu-24.04-arm` runner，但不会直接把 Ubuntu 当成 Android。
完整构建发生在固定 digest 的官方 `termux/termux-docker:aarch64` 环境中，最终文件由
Bionic `/system/bin/linker64` 实际执行，并依次通过 FFF、watcher、PTY 和 TUI smoke。

- PR：工具和 graph 回归测试；
- push 到 `main`：完整 Bionic 构建，上传 14 天 Action artifact；
- 每 6 小时：检查官方最新版，新版本构建通过后自动创建 GitHub Release；
- 手动运行：可指定版本，并选择是否发布。

详细的权限和运行环境说明见 [`docs/ci.md`](docs/ci.md)。

## 发布门禁

- Release 输入和所有源码归档均固定 SHA-256；
- 原生资产按 graph 模块名精确匹配，零匹配或多匹配都会失败；
- FFF wrapper 改写要求所有 minified 模式数量完全一致；
- 任一内嵌 ELF 含 glibc loader、`libc.so.6` 或非白名单依赖即失败；
- 候选通过版本、graph、ELF 与 TUI 验证前不会替换 `dist/opencode`；
- OpenCode 自带升级器已改为查询本项目 Release，并调用同一个 SHA-256 校验安装器；
  不会安装官方 Linux/glibc 文件。

原生资产哈希和技术细节见 [`docs/native-assets.md`](docs/native-assets.md)。

第三方组件及许可见 [`THIRD_PARTY.md`](THIRD_PARTY.md)。
