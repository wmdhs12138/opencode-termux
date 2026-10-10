# 维护手册

给维护者（包括以后的自己）。发布都在 CI 里完成；手机上做的是改补丁和工具、跑测试，以及用现成的原生组件做本地构建验证。

```bash
make test                        # 回归测试，几秒，不联网
```

## 上游发新版本

每天 03:17 UTC 的 CI 会发现新版本，构建、在 termux-docker 里验收通过后自动发布，不需要人工操作。构建失败时按失败的步骤处理：

| 失败在 | 通常意味着 | 怎么办 |
| --- | --- | --- |
| `updater ... match mismatch` | 上游改了升级命令或安装服务的写法 | 在模块图里找到新写法，更新 `tools/patch_updater_graph.py` 的正则，在 `tests/test_updater_patch.py` 加一个该版本的样例 |
| 原生组件审计 | 图里出现了新的原生模块，或某个组件的名字变了 | 看 `work/build/native-after.json`，见 [native-assets.md](native-assets.md) |
| `update command smoke failed` | 注入的 `update` 命令在运行时出错，多半是捕获的压缩名不在作用域里 | 看 `work/build/update-smoke.log` |
| 嫁接或 `--version` 段错误 | 模块图格式随 Bun 版本变了 | 需要更新的 Bun 底座，见下文 |

手动重跑：`gh workflow run build.yml -f version=<版本>`。

## 在手机上本地构建

原生组件要用 NDK、Rust 和 Zig 编译，手机上一般没有。验证 Bun 底座或图补丁时，可以直接复用某个 Release 里已经验收过的组件：

```bash
make fetch VERSION=1.18.35                      # 官方 linux-arm64，按 GitHub 的 digest 校验
make fetch-bun                                  # versions.json 锁定的 Bun 底座
mkdir -p "$TMPDIR/oc/bin"                      # 只为取组件，不碰 $PREFIX/bin
curl -fsSL https://raw.githubusercontent.com/wmdhs12138/opencode-termux/main/install.sh \
  | PREFIX="$TMPDIR/oc" VERSION=1.18.35 bash
python3 tools/dump_native_assets.py "$TMPDIR/oc/bin/opencode" work/native-release > work/native-release.env
env $(cat work/native-release.env) REQUIRE_ALL_BIONIC=1 bash scripts/build.sh
```

`scripts/build.sh` 会做完整的检查：原生组件审计、嫁接校验、`--version`、`update` 命令冒烟和真实 TUI 冒烟，全部通过才替换 `dist/opencode`。组件本身的 FFF / watcher / PTY 冒烟用的是 `work/bun-android/bun`，可以对取出来的文件单独运行（见 `scripts/build-*.sh` 末尾）。

## 更换 Bun 底座

底座是 Bun 官方 Release 里的 `bun-linux-aarch64-android.zip`，`versions.json` 按 URL 和 SHA-256 锁定（`archive_sha256` 对照 Release 的 `SHASUMS256.txt`）。改完 `versions.json` 后：

1. `make fetch-bun`，确认下载和两个哈希都对得上；
2. 按上一节在手机上本地构建，并对取出来的组件跑一遍三个冒烟；
3. 推送，让 CI 从源码重新编译组件并在 termux-docker 里验收；
4. 通过后用 `recut` 重新发布当前版本（见下文）。

原生组件编译时不依赖 Bun，Bun 只用来跑它们的冒烟测试，所以换底座不需要改组件。

## 发版

- `vX.Y.Z`：一个 OpenCode 版本第一次通过验收时自动发布。
- `vX.Y.Z-rN`：工具链（Bun 底座、补丁、原生组件、`tools/`、`scripts/`）改了但 OpenCode 版本没变时，手动重新发布：

  ```bash
  gh workflow run build.yml -f version=latest -f recut=true
  ```

  不急的话，改动会随下一个 OpenCode 版本自然发布。
- 只有最高的 OpenCode 版本会成为 Latest，所以重新发布旧版本不会让安装回退。
- 发布说明列出相对上一个 Release 的工具链变更（不含 `docs/`、`tests/` 和 Markdown）。
- 推送到 `main` 会触发完整的 Bionic 构建；只改文档时在提交信息里写 `[skip ci]`。有构建正在发布时别推会触发构建的提交。

## 兼容约束

已经装在用户手机上的 `opencode` 会在 `upgrade` 时从 `main` 下载 `install.sh` 来运行，所以下面这些对它们是接口：

- `install.sh` 的环境变量 `VERSION`（`latest`、`X.Y.Z`，或 `X.Y.Z-rN`）、`PREFIX`、`OPENCODE_TERMUX_REPO`。旧版本只会传 `X.Y.Z`，它表示这个版本最新的那次构建；
- Release 附件名 `opencode-termux-v<版本>-android-aarch64.zip`、`.zip.sha256` 和 `build-manifest.json`，`-rN` 重发时附件名里仍是不带 `-rN` 的版本；
- 清单字段 `tag_name`（`Installation.latest()` 读它，必须保持 `vX.Y.Z`，带上 `-rN` 会让 TUI 每次启动都认为有新版本并在后台重装）和 `output_sha256`（`install.sh`、`update`、`upgrade` 按它判断是否同一个构建）。

v1.18.35 及更早的二进制自带的 `upgrade` 只比较版本，会跳过同版本的 `-rN`；它们要重新运行一次安装命令，之后的版本就按哈希判断了。

## 踩过的坑

- **嫁接时底座文件的尾巴会落进 `.bss`。** 扩展可写段的 `p_filesz` 后，底座原本放在段尾之后的 `.symtab`、节头表会成为 `.bss` 的初值。官方 Bun 1.4.3 上任何图都会在启动时于 `0x0` 段错误；`tools/revive_patch.py` 已修复（也提交给了上游 Hope2333/opencode-termux#34）。
- **termux-docker 里没有 `/usr/bin/env`。** `make test` 也会在 Bionic 容器里跑，测试造的假命令要用 `sys.executable` 或 `shutil.which("bash")` 的绝对路径做解释器。
- **api.github.com 匿名每小时 60 次。** 手机常在运营商 NAT 后面，很快用完；安装器和更新检查都只用 Release 页面的跳转和 Release 附件，它们不受这个限制。
- **压缩名每个版本都变。** 补丁一律从上游自己的调用里捕获名字（见 `patch_updater_graph.py` 的说明），不要写死。
- Android 上 `/tmp` 不可写，临时文件放 `$TMPDIR`。
