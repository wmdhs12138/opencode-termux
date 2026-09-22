# Architecture

## 为什么采用 graph transplant

OpenCode 和 Claude Code 都由 Bun standalone 承载。现有探针已经在官方 OpenCode
v1.18.32 图上验证：
trailer、Offsets、52 字节模块记录和 graph-relative StringPointer 与 Bun >= 1.4 工具链兼容。

源码构建仍然有价值，但不能把“Bun 编译成功”视为 Bionic 产物：bundler 会按
`linux-arm64` 选择 glibc 平台包。最终 graph 必须经过独立审计和重写。

## 资产替换策略

`replace_native_asset.py` 不覆盖原 slot。它把新 ELF 追加到 Offsets 结构之前，再只修改目标
模块的 contents StringPointer。这样：

- 新资产可以比旧资产大；
- 其他 StringPointer 不移动；
- 模块表和可选记录不需要重排；
- 原资产保留为不可达数据，便于差异审计。

## 发布门禁

正式产物必须同时满足：

1. graph 结构验证；
2. 所有内嵌 ELF 都是 AArch64；
3. 所有可执行原生资产都没有 glibc interpreter/soname；
4. OpenTUI 与 FFF 导出符号满足当前 JS FFI；
5. `--version` 与输入版本一致；
6. TUI 在隔离 HOME 中渲染真实帧；
7. service、PTY 和 watcher 功能 smoke 通过。

`make build-strict` 会先从固定源码构建四个替换资产，再修补 FFF wrapper、做 graph
替换、严格 ELF 审计、graft 验证、版本验证和 TUI smoke。只有完整链路成功才会原子替换
`dist/opencode`。
