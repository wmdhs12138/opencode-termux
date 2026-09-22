import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from graph_format import GraphError
from patch_updater_graph import (
    METHOD_AFTER,
    METHOD_BEFORE,
    TERMUX_INSTALLER,
    TERMUX_RELEASES,
    UPSTREAM_INSTALLER,
    UPSTREAM_RELEASES,
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


if __name__ == "__main__":
    unittest.main()
