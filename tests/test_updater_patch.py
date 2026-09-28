import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

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
                self.assertIn(source.split("cli.")[0], result)
                update = result[: result.index(f"var {command}=")]
                self.assertIn('command:"update"', update)
                self.assertIn(f'{ui}.empty(),{ui}.println({ui}.logo("  "))', update)
                self.assertIn('_D("Update")', update)
                self.assertIn("await Lu.latest()", update)
                self.assertIn(f"{log}.error(`Update check failed", update)
                self.assertIn(f"{log}.info(`Current: ${{gD}}`)", update)
                self.assertIn("Run opencode upgrade to install it", update)
                self.assertIn('typeof termuxLatest!=="string"', update)
                self.assertIn('g("Done")', update)
                self.assertIn('command:"upgrade [target]"', result)


if __name__ == "__main__":
    unittest.main()
