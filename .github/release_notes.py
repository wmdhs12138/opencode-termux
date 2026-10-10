#!/usr/bin/env python3
"""Generate concise GitHub release notes from the Bionic build manifest.

  release_notes.py <out.md> --manifest M --tag vX.Y.Z[-rN] --commit SHA
                            --predecessor TAG|- --changelog FILE
"""
import argparse
import json
import re

INSTALL = "curl -fsSL https://raw.githubusercontent.com/wmdhs12138/opencode-termux/main/install.sh | bash"


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def release_notes(manifest, tag, commit, predecessor, changelog):
    m = manifest
    ver = m.get("opencode", "?")
    bun = m.get("base_bun") or {}
    accepted = (
        m.get("release_eligible") is True
        and m.get("tui_smoke") == "pass"
        and (m.get("native_assets") or {}).get("result") == "pass"
    )
    if accepted:
        verification = "Termux Bionic 容器内原生组件 ELF 审计、FFF / watcher / PTY 冒烟和真实 TUI 启动全部通过。"
    else:
        verification = "⚠️ 未完成 Bionic 运行验收。"

    recut = re.search(r"-r(\d+)$", tag)
    if recut:
        what = (f"\n这是 {ver} 的第 {recut.group(1)} 次重新发布：OpenCode 版本不变，构建工具链有更新。"
                "`opencode upgrade` 按二进制哈希判断，会识别并安装；"
                "旧版本自带的 `opencode upgrade` 会跳过同一版本，请重新运行一次下面的安装命令。\n")
    else:
        what = ""
    if predecessor and predecessor != "-":
        scope = f"相对 `{predecessor}` 的工具链变更："
    else:
        scope = "工具链变更："

    return f"""# OpenCode {ver} · Termux

验收：{verification}
{what}
安装或更新：

```bash
{INSTALL}
```

已安装的可以运行 `opencode upgrade`。

| 项目 | 值 |
|---|---|
| 官方 opencode-linux-arm64 SHA-256 | `{m.get("input_sha256", "?")}` |
| opencode 二进制 SHA-256 | `{m.get("output_sha256", "?")}` |
| Bun 底座 | `{bun.get("version", "?")}` |
| 工具链提交 | `{commit[:12] or "?"}` |

{scope}

{changelog.strip() or "（无）"}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--predecessor", default="-")
    ap.add_argument("--changelog", required=True)
    a = ap.parse_args()

    try:
        with open(a.changelog) as f:
            changelog = f.read()
    except OSError:
        changelog = ""
    notes = release_notes(load(a.manifest), a.tag, a.commit, a.predecessor, changelog)
    with open(a.out, "w") as f:
        f.write(notes)
    print(f"wrote {a.out} ({len(notes)} bytes)")


if __name__ == "__main__":
    main()
