#!/usr/bin/env python3
"""Render an OpenCode frame with its private server in an isolated home."""

from __future__ import annotations

import os
import pty
import re
import select
import signal
import sys
import tempfile
import time


MARKERS = ("OpenCode", "Ask anything", "commands", "agents")
MIN_BYTES = 256


def command_lines() -> dict[int, tuple[str, ...]]:
    result = {}
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            raw = open(f"/proc/{name}/cmdline", "rb").read()
        except OSError:
            continue
        args = tuple(part.decode("utf-8", "replace") for part in raw.split(b"\0") if part)
        if args:
            result[int(name)] = args
    return result


def process_home(pid: int) -> str | None:
    try:
        raw = open(f"/proc/{pid}/environ", "rb").read()
    except OSError:
        return None
    for item in raw.split(b"\0"):
        if item.startswith(b"HOME="):
            return item[5:].decode("utf-8", "replace")
    return None


def cleanup_services(before: set[int], smoke_home: str) -> list[int]:
    """Stop only services created with this smoke run's isolated HOME."""
    found = []
    for pid, args in command_lines().items():
        if pid in before or len(args) < 3 or args[1:3] != ("serve", "--service"):
            continue
        if process_home(pid) != smoke_home:
            continue
        found.append(pid)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 2
    while found and time.monotonic() < deadline:
        found = [pid for pid in found if os.path.exists(f"/proc/{pid}")]
        if found:
            time.sleep(0.05)
    for pid in found:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return found


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("usage: tui_smoke.py <opencode> [seconds]", file=sys.stderr)
        return 2
    binary = os.path.realpath(sys.argv[1])
    duration = float(sys.argv[2]) if len(sys.argv) == 3 else 15.0
    before = set(command_lines())
    output = bytearray()
    status = None
    exited_early = False
    leaked_services = []
    with tempfile.TemporaryDirectory(prefix="opencode-tui-smoke-") as home:
        bindir = f"{home}/bin"
        os.mkdir(bindir)
        os.symlink(binary, f"{bindir}/opencode")
        env = dict(os.environ)
        env.update(
            {
                "HOME": home,
                "XDG_CONFIG_HOME": f"{home}/config",
                "XDG_CACHE_HOME": f"{home}/cache",
                "XDG_DATA_HOME": f"{home}/data",
                "TERM": "xterm-256color",
                "PATH": f"{bindir}:{env.get('PATH', '')}",
            }
        )
        pid, fd = pty.fork()
        if pid == 0:
            os.execve(binary, [binary], env)
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            ready, _, _ = select.select([fd], [], [], min(0.25, deadline - time.monotonic()))
            if ready:
                try:
                    output.extend(os.read(fd, 65536))
                except OSError:
                    pass
            done, child_status = os.waitpid(pid, os.WNOHANG)
            if done:
                status = child_status
                exited_early = True
                break
        if status is None:
            try:
                os.write(fd, b"\x03")
            except OSError:
                pass
            time.sleep(0.5)
            done, child_status = os.waitpid(pid, os.WNOHANG)
            if done:
                status = child_status
            else:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                _, status = os.waitpid(pid, 0)
        try:
            os.close(fd)
        except OSError:
            pass
        leaked_services = cleanup_services(before, home)
    text = output.decode("utf-8", "replace")
    visible = re.sub(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|.)", " ", text)
    visible = " ".join(visible.split())
    markers = [item for item in MARKERS if item in visible]
    rendered = len(output) >= MIN_BYTES and "\x1b" in text and bool(markers)
    print(
        f"bytes_captured={len(output)} status={status} exited_early={exited_early} "
        f"markers={markers} leaked_services={leaked_services}"
    )
    if exited_early:
        print("smoke: FAIL: OpenCode exited early", file=sys.stderr)
        return 1
    if not rendered:
        print("smoke: FAIL: no recognizable OpenCode frame", file=sys.stderr)
        return 1
    print("smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
