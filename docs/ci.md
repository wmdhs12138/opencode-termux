# CI architecture

GitHub-hosted Ubuntu runners use glibc, so an AArch64 runner alone is not an
Android runtime. The release workflow runs the build inside the official
[`termux/termux-docker`](https://github.com/termux/termux-docker) AArch64 image,
which supplies Bionic libc, `/system/bin/linker64`, AOSP libraries and a Termux
filesystem layout.

```text
ubuntu-24.04-arm GitHub runner
└── pinned termux/termux-docker image
    ├── Termux clang + Android NDK libraries
    ├── Ubuntu proot (host-side Rust 1.90 and Zig 0.15.2 only)
    ├── build four Bionic native assets
    ├── graft official OpenCode graph onto Bionic Bun
    ├── execute FFF, watcher and PTY smoke tests
    └── execute the real OpenCode TUI smoke test
```

The Ubuntu proot is a compiler host, not the runtime under test. Every native
library and the final `opencode` executable are loaded by Bionic inside the
Termux container.

This is a real Bionic userspace, but not a complete Android device: it has no
Dalvik/ART, Android framework services or app sandbox. OpenCode only needs the
native libc/dl/m/log/z, filesystem, PTY and inotify surface covered by the
smoke tests. A physical-device run remains the final reference when changing
the Bun base, NDK generation or native ABI patches.

## Triggers

- Pull requests run the Python and shell regression suite.
- Pushes to `main` also produce a 14-day Action artifact.
- The six-hour schedule checks the official OpenCode latest release. A version
  without an existing repository tag is built, tested and published.
- `workflow_dispatch` accepts an explicit version. Set `publish=true` to create
  a release after all Bionic checks pass.

## Trust boundaries

- The Termux image is pinned by OCI digest, not a mutable tag.
- OpenCode release assets, Bionic Bun and all native source archives are checked
  against pinned SHA-256 values or GitHub release digests.
- The build job has read-only repository permission.
- Only the final release job receives `contents: write`.
- A release is never created when the TUI smoke is skipped or fails.

The cross-build `SKIP_RUN=1` mode remains available for structural debugging,
but it sets `release_eligible=false` and is not used by the release workflow.
