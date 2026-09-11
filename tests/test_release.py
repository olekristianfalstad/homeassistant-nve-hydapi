"""Check shipped translation placeholders and compatibility metadata."""

import json
from pathlib import Path
from string import Formatter
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "nve_hydapi"


def leaves(data, prefix=""):
    result = {}
    for key, value in data.items():
        path = prefix + key
        if isinstance(value, dict):
            result.update(leaves(value, path + "."))
        else:
            result[path] = value
    return result


class ReleaseTests(TestCase):
    def test_translations_have_matching_keys_and_placeholders(self):
        strings = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
        en = json.loads((COMPONENT / "translations/en.json").read_text(encoding="utf-8"))
        nb = json.loads((COMPONENT / "translations/nb.json").read_text(encoding="utf-8"))
        self.assertEqual(strings, en)
        english, norwegian = leaves(en), leaves(nb)
        self.assertEqual(english.keys(), norwegian.keys())
        for key in english:
            with self.subTest(key=key):
                fields = lambda value: {
                    field for _, field, _, _ in Formatter().parse(value) if field
                }
                self.assertEqual(fields(english[key]), fields(norwegian[key]))
        for step in ("reauth_confirm", "reconfigure"):
            self.assertIn("api_key", nb["config"]["step"][step]["data"])

    def test_minimum_version_matches_test_matrix(self):
        hacs = json.loads((ROOT / "hacs.json").read_text())
        workflow = (ROOT / ".github/workflows/tests.yml").read_text()
        self.assertIn('homeassistant: "' + hacs["homeassistant"] + '"', workflow)
