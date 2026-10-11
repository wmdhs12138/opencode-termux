#!/usr/bin/env python3
"""Search files through OpenCode's own server, in an isolated home.

The FFF wrapper bundled into the binary is patched for Android's tagged heap
pointers (patches/fff-bun-android.patch); this runs a real search through it:
an unpatched wrapper crashes Bun on the first result it reads.

  serve_smoke.py OPENCODE [TIMEOUT_SECONDS]
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


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

    with tempfile.TemporaryDirectory(prefix="opencode-serve-smoke.") as tmp:
        home = os.path.join(tmp, "home")
        project = os.path.join(tmp, "project")
        os.makedirs(home)
        os.makedirs(os.path.join(project, "src"))
        with open(os.path.join(project, "README.md"), "w") as f:
            f.write("readme\n")
        with open(os.path.join(project, "src", "main.ts"), "w") as f:
            f.write("export {}\n")
        env = {key: value for key, value in os.environ.items() if not key.startswith("XDG_")}
        env["HOME"] = home
        # The server requires Basic auth as "opencode"; it generates a password
        # unless one is given.
        password = secrets.token_urlsafe(24)
        env["OPENCODE_SERVER_PASSWORD"] = password
        credentials = base64.b64encode(f"opencode:{password}".encode()).decode()
        port = free_port()
        query = urllib.parse.urlencode({"query": "readme", "location[directory]": project})
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/fs/find?{query}",
            headers={"Authorization": f"Basic {credentials}"},
        )

        log_path = os.path.join(tmp, "serve.log")
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
                        with urllib.request.urlopen(request, timeout=10) as response:
                            body = response.read().decode("utf-8", "replace")
                        if "README.md" in body:
                            break
                        error = "README.md not in the results yet"
                    except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
                        error = str(exc)
                    time.sleep(0.5)
            finally:
                exited = server.poll()
                if exited is None:
                    os.killpg(server.pid, signal.SIGTERM)
                    try:
                        server.wait(5)
                    except subprocess.TimeoutExpired:
                        os.killpg(server.pid, signal.SIGKILL)
                        server.wait()

        found = "README.md" in body
        print(json.dumps({
            "file_search": "pass" if found else "fail",
            "server_exited_early": exited,
            "error": None if found else error,
            "response": body[:400],
        }))
        if not found:
            with open(log_path, "rb") as log:
                sys.stderr.write(log.read()[-4000:].decode("utf-8", "replace"))
        return 0 if found else 1


if __name__ == "__main__":
    raise SystemExit(main())
