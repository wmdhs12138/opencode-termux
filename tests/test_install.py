#!/usr/bin/env python3
"""install.sh against a fake GitHub: release resolution, re-cuts, hash checks.

The fakes use absolute interpreter paths because `make test` also runs inside
termux-docker, which has no /usr/bin/env.
"""

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"
BASH = shutil.which("bash")

FAKE_CURL = f"""#!{sys.executable}
# Serves https://github.com/<repo>/releases/... from $FAKE_GH:
#   $FAKE_GH/latest            the tag /releases/latest redirects to
#   $FAKE_GH/<tag>/<asset>     release assets
import os, shutil, sys
args, out, fmt, url = sys.argv[1:], None, None, None
i = 0
while i < len(args):
    a = args[i]
    if a in ("-o", "-w", "--retry", "--retry-delay", "-C"):
        if a == "-o": out = args[i + 1]
        if a == "-w": fmt = args[i + 1]
        i += 2
        continue
    if a.startswith("http"): url = a
    i += 1
gh = os.environ["FAKE_GH"]
with open(os.path.join(gh, "requests.log"), "a") as log:
    log.write(url + "\\n")
releases = "https://github.com/" + os.environ["FAKE_REPO"] + "/releases/"
if url == releases + "latest":
    tag = open(os.path.join(gh, "latest")).read().strip()
    if out: open(out, "w").close()
    if fmt: sys.stdout.write(releases + "tag/" + tag)
    sys.exit(0)
if url.startswith(releases + "download/"):
    src = os.path.join(gh, url[len(releases + "download/"):])
    if os.path.isfile(src):
        shutil.copyfile(src, out)
        sys.exit(0)
sys.exit(22)
"""


class InstallTests(unittest.TestCase):
    REPO = "owner/opencode-termux"

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.gh = self.tmp / "gh"
        self.gh.mkdir()
        self.prefix = self.tmp / "prefix"
        (self.prefix / "bin").mkdir(parents=True)
        fake = self.tmp / "fake-bin"
        fake.mkdir()
        for name, body in {
            "curl": FAKE_CURL,
            "uname": f"#!{BASH}\necho aarch64\n",
            "getprop": f"#!{BASH}\necho 34\n",
        }.items():
            (fake / name).write_text(body)
            (fake / name).chmod(0o755)
        self.path = f"{fake}:{os.environ['PATH']}"

    def release(self, tag, label=None, manifest_sha=None):
        """A release laid out like the real ones; returns the binary hash."""
        version = tag[1:].split("-r")[0]
        package = f"opencode-termux-v{version}-android-aarch64"
        binary = f"#!{BASH}\necho '{label or tag} (OpenCode {version})'\n".encode()
        out = self.gh / tag
        out.mkdir()
        with zipfile.ZipFile(out / f"{package}.zip", "w") as bundle:
            info = zipfile.ZipInfo(f"{package}/opencode")
            info.external_attr = 0o755 << 16
            bundle.writestr(info, binary)
        digest = hashlib.sha256((out / f"{package}.zip").read_bytes()).hexdigest()
        (out / f"{package}.zip.sha256").write_text(f"{digest}  {package}.zip\n")
        sha = hashlib.sha256(binary).hexdigest()
        (out / "build-manifest.json").write_text(json.dumps(
            {"opencode": version, "tag_name": f"v{version}",
             "output_sha256": manifest_sha or sha}, indent=2))
        return sha

    def latest(self, tag):
        (self.gh / "latest").write_text(tag)

    def install(self, version=None, **env):
        full = dict(os.environ, PATH=self.path, PREFIX=str(self.prefix), TMPDIR=str(self.tmp),
                    FAKE_GH=str(self.gh), FAKE_REPO=self.REPO, OPENCODE_TERMUX_REPO=self.REPO,
                    **env)
        full.pop("VERSION", None)
        if version:
            full["VERSION"] = version
        return subprocess.run([BASH, str(INSTALL)], env=full, text=True, capture_output=True)

    def installed(self):
        path = self.prefix / "bin" / "opencode"
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

    def requests(self):
        log = self.gh / "requests.log"
        return log.read_text().split() if log.exists() else []

    def assertOk(self, proc):
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_fresh_install_takes_the_latest_release(self):
        self.release("v1.2.2")
        sha = self.release("v1.2.3")
        self.latest("v1.2.3")
        proc = self.install()
        self.assertOk(proc)
        self.assertEqual(self.installed(), sha)
        self.assertIn("v1.2.3 (OpenCode 1.2.3)", proc.stdout)

    def test_matching_install_downloads_nothing_but_the_manifest(self):
        self.release("v1.2.3")
        self.latest("v1.2.3")
        self.assertOk(self.install())
        (self.gh / "requests.log").unlink()
        proc = self.install()
        self.assertOk(proc)
        self.assertIn("already up to date (v1.2.3)", proc.stdout)
        self.assertFalse([r for r in self.requests() if r.endswith(".zip")])

    def test_recut_of_the_installed_version_is_installed(self):
        self.release("v1.2.3")
        self.latest("v1.2.3")
        self.assertOk(self.install())
        sha = self.release("v1.2.3-r1")
        self.latest("v1.2.3-r1")
        proc = self.install()
        self.assertOk(proc)
        self.assertEqual(self.installed(), sha)
        self.assertIn("Installed:", proc.stdout)

    def test_plain_version_means_its_newest_build(self):
        # What `opencode upgrade` sends: the version, never the tag.
        self.release("v1.2.3")
        sha = self.release("v1.2.3-r1")
        self.latest("v1.2.3-r1")
        self.assertOk(self.install("1.2.3"))
        self.assertEqual(self.installed(), sha)

    def test_plain_older_version_probes_its_recuts(self):
        self.release("v1.2.2")
        self.release("v1.2.2-r1")
        sha = self.release("v1.2.2-r2")
        self.release("v1.2.3")
        self.latest("v1.2.3")
        self.assertOk(self.install("v1.2.2"))
        self.assertEqual(self.installed(), sha)

    def test_exact_recut_is_honored(self):
        sha = self.release("v1.2.3-r1")
        self.release("v1.2.3-r2")
        self.latest("v1.2.3-r2")
        self.assertOk(self.install("1.2.3-r1"))
        self.assertEqual(self.installed(), sha)

    def test_bad_version_is_rejected_before_any_download(self):
        proc = self.install("1.2")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("bad version", proc.stderr)
        self.assertEqual(self.requests(), [])

    def test_binary_that_does_not_match_the_manifest_is_not_installed(self):
        self.release("v1.2.3", manifest_sha="0" * 64)
        self.latest("v1.2.3")
        (self.prefix / "bin" / "opencode").write_text("old")
        proc = self.install()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("does not match", proc.stderr)
        self.assertEqual((self.prefix / "bin" / "opencode").read_text(), "old")

    def test_force_reinstalls_a_matching_binary(self):
        self.release("v1.2.3")
        self.latest("v1.2.3")
        self.assertOk(self.install())
        proc = self.install(OPENCODE_TERMUX_FORCE="1")
        self.assertOk(proc)
        self.assertIn("Installed:", proc.stdout)


if __name__ == "__main__":
    unittest.main()
