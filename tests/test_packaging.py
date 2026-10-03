import json
from pathlib import Path
import re
import unittest

import yaml

from mylibrary import __version__

ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_manifests_share_the_runtime_version(self):
        for manifest in ("plugin.json", ".codex-plugin/plugin.json"):
            self.assertEqual(json.loads((ROOT / manifest).read_text())["version"], __version__, manifest)
        self.assertIn('version = {attr = "mylibrary.__version__"}', (ROOT / "pyproject.toml").read_text())

    def test_every_skill_declares_a_runtime_it_can_run_on(self):
        current = tuple(int(part) for part in __version__.split("."))
        for path in sorted(ROOT.glob("skills/*/SKILL.md")):
            fields = yaml.safe_load(re.match(r"\A---\n(.*?)\n---\n", path.read_text(), re.S).group(1))
            requirement = fields["metadata"]["runtime"]
            self.assertTrue(requirement.startswith("mylibrary-tools>="), path)
            needed = tuple(int(part) for part in requirement.split(">=")[1].split("."))
            self.assertLessEqual(needed, current, path)
            self.assertEqual(needed[:2], current[:2], f"{path} should require the minor version it was written for")
