import argparse
from pathlib import Path
import re
import unittest

import yaml

from mylibrary import cli

ROOT = Path(__file__).resolve().parents[1]
DOCS = sorted(ROOT.glob("skills/*/SKILL.md")) + sorted(ROOT.glob("skills/*/references/*.md")) + sorted(ROOT.glob("_stdlib/*.md"))


def parser_commands():
    captured = {}
    original = argparse.ArgumentParser.parse_args

    def capture(self, args=None, namespace=None):
        captured["parser"] = self
        raise SystemExit(0)

    argparse.ArgumentParser.parse_args = capture
    try:
        cli.main([])
    except SystemExit:
        pass
    finally:
        argparse.ArgumentParser.parse_args = original
    subparsers = next(action for action in captured["parser"]._actions if isinstance(action, argparse._SubParsersAction))
    return {name: {option for action in sub._actions for option in action.option_strings}
            for name, sub in subparsers.choices.items()}


class SkillTests(unittest.TestCase):
    def test_frontmatter_names_match_folders(self):
        for path in sorted(ROOT.glob("skills/*/SKILL.md")):
            fields = yaml.safe_load(re.match(r"\A---\n(.*?)\n---\n", path.read_text(), re.S).group(1))
            self.assertEqual(fields["name"], path.parent.name)
            self.assertTrue(fields["description"].strip())

    def test_relative_links_resolve(self):
        broken = []
        for path in DOCS:
            prose = re.sub(r"```.*?```|`[^`\n]*`", "", path.read_text(), flags=re.S)
            for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", prose):
                if not re.match(r"[a-z]+:", target) and not (path.parent / target).exists():
                    broken.append(f"{path.relative_to(ROOT)} -> {target}")
        self.assertEqual(broken, [])

    def test_documented_commands_and_flags_exist(self):
        commands, unknown = parser_commands(), []
        for path in DOCS:
            for match in re.finditer(r"mylibrary ((?:--vault \S+ )?[a-z][a-z-]*)([^`\n]*)", path.read_text()):
                name, rest = match.group(1).split()[-1], match.group(2)
                if name not in commands:
                    unknown.append(f"{path.relative_to(ROOT)}: {match.group(0).strip()}")
                    continue
                unknown += [f"{path.relative_to(ROOT)}: {match.group(0).strip()}"
                            for flag in re.findall(r"(?<![\w-])(--[a-z-]+)", rest) if flag not in commands[name]]
        self.assertEqual(unknown, [])
