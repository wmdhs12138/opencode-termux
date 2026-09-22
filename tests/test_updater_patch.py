import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from graph_format import GraphError
from patch_updater_graph import (
    COMMAND_AFTER,
    COMMAND_BEFORE,
    METHOD_AFTER,
    METHOD_BEFORE,
    REGISTRATION_AFTER,
    REGISTRATION_BEFORE,
    TERMUX_INSTALLER,
    TERMUX_RELEASES,
    UPSTREAM_INSTALLER,
    UPSTREAM_RELEASES,
    patch_command,
    patch_updater,
)


class UpdaterPatchTests(unittest.TestCase):
    def test_routes_install_and_latest_to_termux(self):
        source = "|".join((UPSTREAM_INSTALLER, UPSTREAM_RELEASES, METHOD_BEFORE))
        result = patch_updater(source.encode()).decode()
        self.assertIn(TERMUX_INSTALLER, result)
        self.assertIn(TERMUX_RELEASES, result)
        self.assertIn(METHOD_AFTER, result)
        self.assertNotIn(UPSTREAM_INSTALLER, result)
        self.assertNotIn(UPSTREAM_RELEASES, result)

    def test_rejects_unknown_upstream_layout(self):
        with self.assertRaises(GraphError):
            patch_updater(b"upstream changed")

    def test_update_checks_and_upgrade_installs(self):
        source = f"{COMMAND_BEFORE}body|{REGISTRATION_BEFORE}"
        result = patch_command(source.encode()).decode()
        self.assertIn(COMMAND_AFTER, result)
        self.assertIn(REGISTRATION_AFTER, result)
        self.assertIn('command:"update"', result)
        self.assertIn("Run opencode upgrade to install it", result)
        self.assertIn("Update check failed", result)
        self.assertIn('typeof D!=="string"', result)
        self.assertIn('command:"upgrade [target]"', result)


if __name__ == "__main__":
    unittest.main()
