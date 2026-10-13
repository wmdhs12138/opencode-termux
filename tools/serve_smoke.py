#!/usr/bin/env python3
"""Search files through OpenCode's own server, in an isolated home.

The FFF wrapper bundled into the binary is patched for Android's tagged heap
pointers (patches/fff-bun-android.patch); this runs a real search through it:
an unpatched wrapper crashes Bun on the first result it reads, and again when
the server destroys the instance on shutdown.

OpenCode 2 only searches with FFF inside a repository and uses ripgrep
elsewhere, so the project is a git repository, the server has to report it as
one, and it has to survive the search and its own shutdown.

  serve_smoke.py OPENCODE [TIMEOUT_SECONDS]
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

# How a Bun panic ends the process: its handler re-raises the signal.
CRASH_SIGNALS = {-signal.SIGSEGV, -signal.SIGBUS, -signal.SIGILL, -signal.SIGABRT, -signal.SIGTRAP}


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    binary = os.path.abspath(sys.argv[1])
    timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 60
    git = shutil.which("git")
    if git is None:
        print("serve_smoke: git is required: OpenCode only searches with FFF in a repository", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="opencode-serve-smoke.") as tmp:
        home = os.path.join(tmp, "home")
        project = os.path.join(tmp, "project")
        os.makedirs(home)
        os.makedirs(os.path.join(project, "src"))
        with open(os.path.join(project, "README.md"), "w") as f:
            f.write("readme\n")
        with open(os.path.join(project, "src", "main.ts"), "w") as f:
            f.write("export {}\n")
        subprocess.run([git, "init", "-q", project], check=True)
        env = {key: value for key, value in os.environ.items() if not key.startswith("XDG_")}
        env.pop("OPENCODE_DISABLE_FFF", None)
        env["HOME"] = home
        # The server requires Basic auth as "opencode"; it generates a password
        # unless one is given.
        password = secrets.token_urlsafe(24)
        env["OPENCODE_SERVER_PASSWORD"] = password
        credentials = base64.b64encode(f"opencode:{password}".encode()).decode()
        port = free_port()

        def get(path: str, **params: str) -> str:
            query = urllib.parse.urlencode({**params, "location[directory]": project})
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}{path}?{query}",
                headers={"Authorization": f"Basic {credentials}"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.read().decode("utf-8", "replace")

        log_path = os.path.join(tmp, "serve.log")
        vcs = None
        with open(log_path, "wb") as log:
            server = subprocess.Popen(
                [binary, "serve", "--hostname", "127.0.0.1", "--port", str(port)],
                cwd=project, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            body, error = "", "no response"
            deadline = time.monotonic() + timeout
            try:
                while time.monotonic() < deadline and server.poll() is None:
                    try:
                        body = get("/api/fs/find", query="readme")
                        if "README.md" in body:
                            break
                        error = "README.md not in the results yet"
                    except urllib.error.HTTPError as exc:
                        error = f"{exc}: {exc.read().decode('utf-8', 'replace')[:2000]}"
                    except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
                        error = str(exc)
                    time.sleep(0.5)
                if "README.md" in body:
                    try:
                        projects = json.loads(get("/api/project"))
                        vcs = next((p.get("vcs") for p in projects if p.get("canonical") == project), None)
                    except (urllib.error.URLError, ConnectionError, TimeoutError, ValueError) as exc:
                        error = f"could not list projects: {exc}"
                    # A destroyed handle or a stray pointer can crash after the response.
                    time.sleep(1)
            finally:
                exited = server.poll()
                if exited is None:
                    os.killpg(server.pid, signal.SIGTERM)
                    try:
                        server.wait(10)
                    except subprocess.TimeoutExpired:
                        os.killpg(server.pid, signal.SIGKILL)
                        server.wait()

        with open(log_path, "rb") as log:
            server_log = log.read().decode("utf-8", "replace")
        crashed = server.returncode in CRASH_SIGNALS or "panic(" in server_log
        found = "README.md" in body
        if found and vcs != "git":
            error = f"the server reports vcs={vcs!r}, so the search went through ripgrep, not FFF"
        elif found and exited is not None:
            error = f"the server exited ({exited}) during the search"
        elif found and crashed:
            error = f"the server crashed on shutdown ({server.returncode})"
        ok = found and vcs == "git" and exited is None and not crashed
        print(json.dumps({
            "file_search": "pass" if ok else "fail",
            "vcs": vcs,
            "server_exited_early": exited,
            "shutdown": server.returncode,
            "crashed": crashed,
            "error": None if ok else error,
            "response": body[:400],
        }))
        if not ok:
            sys.stderr.write(server_log[-4000:])
            # OpenCode's own log, under the isolated home.
            for directory, _, files in os.walk(home):
                for name in files:
                    if name.endswith(".log"):
                        path = os.path.join(directory, name)
                        with open(path, "rb") as log:
                            sys.stderr.write(f"--- {os.path.relpath(path, home)}\n")
                            sys.stderr.write(log.read()[-6000:].decode("utf-8", "replace"))
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
