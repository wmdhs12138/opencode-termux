SHELL := bash
VERSION ?= latest

# Termux:     fetch-bun, build-native, verify
# glibc host: fetch-source, fetch-host-bun, fetch-bun, compile
# (scripts/compile.sh explains why compiling cannot happen inside Termux.)

.PHONY: fetch-source fetch-bun fetch-host-bun build-watcher build-opentui build-fff build-rust-pty build-native compile verify smoke audit test clean

fetch-source:
	bash scripts/fetch-source.sh $(VERSION)

fetch-bun:
	bash scripts/fetch-bun.sh

fetch-host-bun:
	bash scripts/fetch-bun.sh work/bun-host host_bun

build-watcher: fetch-bun
	bash scripts/build-watcher.sh

build-opentui: fetch-bun
	bash scripts/build-opentui.sh

build-fff: fetch-bun
	bash scripts/build-fff.sh

build-rust-pty: fetch-bun
	bash scripts/build-rust-pty.sh

build-native: build-watcher build-opentui build-fff build-rust-pty

compile: fetch-host-bun
	SKIP_RUN=1 bash scripts/fetch-bun.sh
	bash scripts/compile.sh

verify:
	bash scripts/verify.sh

smoke:
	python3 tools/tui_smoke.py dist/opencode 15

audit:
	python3 tools/extract_graph.py dist/opencode work/audit.graph > work/audit-extract.json
	python3 tools/audit_native_assets.py work/audit.graph --report work/audit-native.json

test:
	python3 -m unittest discover -s tests -v
	python3 -m py_compile tools/*.py
	bash -n install.sh scripts/*.sh .github/ci/*.sh

clean:
	flock -n .build.lock -c 'rm -rf work/build work/audit.graph work/audit-*.json dist/.opencode.new dist/compile.json'
