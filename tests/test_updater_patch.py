import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from graph_format import GraphError
from patch_updater_graph import (
    TERMUX_INSTALLER,
    TERMUX_RELEASES,
    UPSTREAM_INSTALLER,
    UPSTREAM_RELEASES,
    patch_command,
    patch_updater,
)


def upgrade_module(command, ui, log, intro="_D", installation="Lu", version="gD", outro="g"):
    # Shape of the minified upstream upgrade command, trimmed to what the
    # patch anchors on. Identifiers change between upstream releases.
    return (
        f'var {command}={{command:"upgrade [target]",describe:"upgrade opencode",'
        f'builder:(D)=>{{return D.positional("target",{{type:"string"}})}},'
        f'handler:async(D)=>{{{ui}.empty(),{ui}.println({ui}.logo("  ")),{ui}.empty(),'
        f'{intro}("Upgrade");let u=await {installation}.method(),F=D.method??u;'
        f'{log}.info("Using method: "+F);'
        f'let C=D.target?D.target.replace(/^v/,""):await {installation}.latest();'
        f'if({version}===C){{{log}.warn(`opencode upgrade skipped: ${{C}} is already installed`),'
        f'{outro}("Done");return}}{outro}("Done")}}}};var k8={{command:"uninstall"}};'
        f'cli.command(a8).command({command}).command(k8)'
    )


class UpdaterPatchTests(unittest.TestCase):
    def test_routes_install_and_latest_to_termux(self):
        method = 'if(process.execPath.includes(P.join(".opencode","bin")))return"curl";'
        source = "|".join((UPSTREAM_INSTALLER, UPSTREAM_RELEASES, method))
        result = patch_updater(source.encode()).decode()
        self.assertIn(TERMUX_INSTALLER, result)
        self.assertIn(TERMUX_RELEASES, result)
        self.assertIn('process.env.PREFIX??"/data/data/com.termux/files/usr"', result)
        self.assertIn('process.execPath.includes(P.join(".opencode","bin"))', result)
        self.assertNotIn(UPSTREAM_INSTALLER, result)
        self.assertNotIn(UPSTREAM_RELEASES, result)

    def test_rejects_unknown_upstream_layout(self):
        with self.assertRaises(GraphError):
            patch_updater(b"upstream changed")
        with self.assertRaises(GraphError):
            patch_command(b'var v8={command:"upgrade [target]",describe:"changed"}')

    def test_update_checks_and_upgrade_installs(self):
        # 1.18.32 and 1.18.33 renamed the command, UI and log identifiers.
        for names in (
            {"command": "v8", "ui": "M", "log": "T"},
            {"command": "d8", "ui": "j", "log": "b"},
        ):
            with self.subTest(**names):
                source = upgrade_module(**names)
                result = patch_command(source.encode()).decode()
                command, ui, log = names["command"], names["ui"], names["log"]
                self.assertIn(
                    f".command(a8).command(TermuxUpdateCommand).command({command})"
                    ".command(k8)",
                    result,
                )
                upstream, patched = source.split("cli.")[0], result.split("cli.")[0]
                skip = "if(gD===C){"
                self.assertEqual(patched.count("if(gD===C&&await TermuxSameBuild(C)){"), 1)
                self.assertTrue(patched.endswith(upstream.replace(skip, skip[:-2] + "&&await TermuxSameBuild(C)){")))
                update = result[: result.index(f"var {command}=")]
                self.assertIn('command:"update"', update)
                self.assertIn(f'{ui}.empty(),{ui}.println({ui}.logo("  "))', update)
                self.assertIn('_D("Update")', update)
                self.assertIn(f'fetch("{TERMUX_RELEASES}")', update)
                self.assertIn('new Bun.CryptoHasher("sha256")', update)
                self.assertIn("Bun.file(process.execPath).stream()", update)
                self.assertIn(f"{log}.error(`Update check failed", update)
                self.assertIn(f"{log}.info(`Current: ${{gD}} (build", update)
                self.assertIn("A rebuilt OpenCode", update)
                self.assertIn("Run opencode upgrade to install it", update)
                self.assertIn('g("Done")', update)
                self.assertIn('command:"upgrade [target]"', result)


def find_bun():
    for candidate in (shutil.which("bun"), ROOT / "work" / "bun-android" / "bun"):
        if candidate and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


@unittest.skipUnless(find_bun(), "needs a Bun runtime")
class UpdaterRuntimeTests(unittest.TestCase):
    """Runs the injected commands in Bun against a stubbed manifest.

    process.execPath is the Bun binary itself, so its hash plays the
    installed build.
    """

    BUN = find_bun()
    SELF = hashlib.sha256(Path(BUN).read_bytes()).hexdigest() if BUN else ""

    def run_commands(self, manifest, version="1.2.3"):
        module = patch_command(upgrade_module("d8", "M", "T").encode()).decode()
        harness = f"""
const out = [];
const M = {{empty() {{}}, println() {{}}, logo() {{ return ""; }}}};
const T = {{info: m => out.push("info " + m), warn: m => out.push("warn " + m),
           error: m => out.push("error " + m)}};
const _D = () => {{}}, g = () => {{}}, a8 = {{}};
const Lu = {{method: async () => "curl", latest: async () => "unused"}};
const cli = {{command() {{ return cli; }}}};
const gD = {json.dumps(version)};
const manifest = {json.dumps(manifest)};
globalThis.fetch = async () => manifest === null
  ? {{ok: false, status: 404}}
  : {{ok: true, json: async () => manifest}};
{module};
await TermuxUpdateCommand.handler();
out.push("--");
await d8.handler({{target: "1.2.3"}});
console.log(JSON.stringify(out));
"""
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "harness.mjs"
            script.write_text(harness)
            proc = subprocess.run([self.BUN, str(script)], text=True, capture_output=True,
                                  timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        update, upgrade = "\n".join(json.loads(proc.stdout)).split("\n--")
        return update, upgrade

    def test_same_build_is_up_to_date_and_upgrade_skips(self):
        update, upgrade = self.run_commands({"tag_name": "v1.2.3", "output_sha256": self.SELF})
        self.assertIn("info OpenCode is up to date", update)
        self.assertIn(f"build {self.SELF[:12]}", update)
        self.assertIn("upgrade skipped", upgrade)

    def test_recut_is_offered_and_upgrade_installs_it(self):
        update, upgrade = self.run_commands({"tag_name": "v1.2.3", "output_sha256": "0" * 64})
        self.assertIn("warn A rebuilt OpenCode 1.2.3 is available", update)
        self.assertNotIn("upgrade skipped", upgrade)

    def test_newer_version_is_offered(self):
        update, _ = self.run_commands({"tag_name": "v1.2.4", "output_sha256": "0" * 64})
        self.assertIn("warn Update available: 1.2.4", update)

    def test_unreachable_manifest_reports_and_upgrade_keeps_skipping(self):
        update, upgrade = self.run_commands(None)
        self.assertIn("error Update check failed: HTTP 404", update)
        self.assertIn("upgrade skipped", upgrade)

if __name__ == "__main__":
    unittest.main()
