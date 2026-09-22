SHELL := bash
VERSION ?= latest
INPUT_ELF ?= $(CURDIR)/work/upstream/opencode
BUN ?= $(CURDIR)/work/bun-android/bun

.PHONY: fetch fetch-bun build-watcher build-opentui build-fff build-rust-pty build-native audit build build-dev build-strict smoke test verify clean

fetch:
	bash scripts/fetch-opencode.sh $(VERSION)

fetch-bun:
	bash scripts/fetch-bun.sh

build-watcher: fetch-bun
	bash scripts/build-watcher.sh

build-opentui:
	bash scripts/build-opentui.sh

build-fff: fetch-bun
	bash scripts/build-fff.sh

build-rust-pty: fetch-bun
	bash scripts/build-rust-pty.sh

build-native: build-watcher build-opentui build-fff build-rust-pty

audit:
	python3 tools/extract_graph.py "$(INPUT_ELF)" work/audit.graph > work/audit-extract.json
	python3 tools/audit_native_assets.py work/audit.graph --report work/audit-native.json

build:
	INPUT_ELF="$(INPUT_ELF)" BUN="$(BUN)" bash scripts/build.sh

build-dev: build-watcher
	INPUT_ELF="$(INPUT_ELF)" BUN="$(BUN)" \
	WATCHER_NODE="$(CURDIR)/work/native/watcher/watcher.node" \
	REQUIRE_ALL_BIONIC=0 bash scripts/build.sh

build-strict: build-native
	INPUT_ELF="$(INPUT_ELF)" BUN="$(BUN)" \
	OPENTUI_SO="$(CURDIR)/work/native/opentui/libopentui.so" \
	FFF_SO="$(CURDIR)/work/native/fff/libfff_c.so" \
	WATCHER_NODE="$(CURDIR)/work/native/watcher/watcher.node" \
	RUST_PTY_SO="$(CURDIR)/work/native/bun-pty/librust_pty_arm64.so" \
	REQUIRE_ALL_BIONIC=1 bash scripts/build.sh

smoke:
	python3 tools/tui_smoke.py dist/opencode 15

test:
	python3 -m unittest discover -s tests -v
	python3 -m py_compile tools/*.py
	bash -n install.sh scripts/*.sh

verify:
	dist/opencode --version
	python3 tools/verify_graft.py dist/opencode

clean:
	flock -n .build.lock -c 'rm -rf work/build work/audit.graph work/audit-*.json dist/.opencode.new'
