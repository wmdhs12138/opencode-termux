# Third-party components

The generated executable combines or transforms the following upstream work:

- [OpenCode](https://github.com/anomalyco/opencode), MIT
- [Bun](https://github.com/oven-sh/bun), MIT
- [OpenTUI](https://github.com/anomalyco/opentui), MIT
- [FFF](https://github.com/dmtrKovalenko/fff), MIT
- [@parcel/watcher](https://github.com/parcel-bundler/watcher), MIT
- [bun-pty](https://github.com/sursaone/bun-pty), MIT
- [portable-pty](https://github.com/wezterm/wezterm/tree/main/pty), MIT

The build also contains transitive Rust, Zig, C and C++ dependencies under
their respective upstream licenses. Source versions and immutable archive
hashes used directly by this project are recorded in `versions.json` and the
release `BUILD-MANIFEST.json`.

`tools/revive_patch.py` is vendored unmodified from
[Hope2333/opencode-termux](https://github.com/Hope2333/opencode-termux), MIT.
