"""Independent offline support-catalog regressions (Python standard library).

Run from any working directory with ``python -m unittest discover -s
output/validation -p test_writing_resources.py``. The sibling website is optional
in toolkit-only copies. These checks do not authenticate or re-fetch sources.
"""
from collections import Counter
import copy
from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
import unittest
from urllib.parse import urlsplit


OUTPUT = Path(__file__).resolve().parents[1]
CATALOG = OUTPUT / "paper-writing/references/writing-resources.json"
SCRIPT = OUTPUT / "paper-writing/scripts/validate_writing_resources.py"
SITE = OUTPUT / "github-paper-review-lab/docs/data/writing-resources.json"
if not SITE.exists():
    SITE = OUTPUT.parent / "docs/data/writing-resources.json"
spec = importlib.util.spec_from_file_location("support_catalog_validator", SCRIPT)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class WritingResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(CATALOG.read_text(encoding="utf-8-sig"))

    def changed_row(self, **changes):
        data = copy.deepcopy(self.catalog)
        data["resources"][0].update(changes)
        return data

    def assert_rejected(self, data):
        with self.assertRaises(ValueError):
            validator.validate(data)

    def test_real_catalog_has_42_distinct_resources_in_eight_populated_categories(self):
        rows = self.catalog["resources"]
        self.assertEqual(validator.validate(self.catalog)["resources"], 42)
        self.assertEqual(len(rows), 42)
        self.assertEqual(len({r["id"] for r in rows}), 42)
        urls = {(urlsplit(r["url"]).hostname.lower(),
                 urlsplit(r["url"]).path.rstrip("/"), urlsplit(r["url"]).query)
                for r in rows}
        self.assertEqual(len(urls), 42)
        self.assertEqual(len(self.catalog["categories"]), 8)
        self.assertEqual(set(r["category"] for r in rows), set(self.catalog["categories"]))

    def test_inspection_levels_preserve_book_and_retrieval_boundaries(self):
        rows = self.catalog["resources"]
        self.assertEqual(Counter(r["inspection_level"] for r in rows), {
            "page-content": 35, "publisher-metadata": 4,
            "author-metadata": 1, "indexed-primary-excerpt": 2,
        })
        books = [r for r in rows if r["resource_type"] == "book"]
        self.assertEqual(len(books), 5)
        self.assertTrue(all(r["inspection_level"] in
                            {"publisher-metadata", "author-metadata"} for r in books))
        self.assertTrue(all("not the full book" in r["limits"] for r in books))
        excerpts = {r["id"] for r in rows if r["inspection_level"] == "indexed-primary-excerpt"}
        self.assertEqual(excerpts, {"cope-ai-authorship", "acm-artifact-badging-1-1"})
        self.assertTrue(all("403" in r["source_note"] for r in rows if r["id"] in excerpts))

    def test_rejects_duplicate_resource_identity(self):
        data = copy.deepcopy(self.catalog)
        data["resources"][1]["id"] = data["resources"][0]["id"]
        self.assert_rejected(data)

    def test_rejects_duplicate_url_despite_host_case_slash_and_fragment(self):
        data = copy.deepcopy(self.catalog)
        first = data["resources"][0]
        first["url"] = "https://EXAMPLE.ORG/a/"
        data["resources"][1]["url"] = "https://example.org/a#section"
        self.assert_rejected(data)

    def test_rejects_missing_evidence_fields_and_unrecognized_schema(self):
        for key in ("source_note", "verified_at", "verification_url", "primary_source", "limits"):
            with self.subTest(missing=key):
                data = copy.deepcopy(self.catalog)
                del data["resources"][0][key]
                self.assert_rejected(data)
        for change in ({"version": 2}, {"undeclared": True}, {"categories": {}}):
            with self.subTest(top_level=change):
                self.assert_rejected(dict(copy.deepcopy(self.catalog), **change))

    def test_rejects_unknown_empty_and_duplicate_profiles(self):
        for value in (["generic"], [], ["theory", "theory"], "theory"):
            with self.subTest(profiles=value):
                self.assert_rejected(self.changed_row(profiles=value))
        for field in ("summary", "source_note", "tasks"):
            with self.subTest(empty=field):
                self.assert_rejected(self.changed_row(**{field: [] if field == "tasks" else " "}))

    def test_rejects_malformed_and_future_source_dates(self):
        for value in ("not-a-date", "2026-02-30", (date.today() + timedelta(days=1)).isoformat()):
            with self.subTest(verified_at=value):
                self.assert_rejected(self.changed_row(verified_at=value))

    def test_rejects_false_or_nonboolean_primary_claim_and_unknown_level(self):
        for value in (False, 1, "true"):
            with self.subTest(primary_source=value):
                self.assert_rejected(self.changed_row(primary_source=value))
        self.assert_rejected(self.changed_row(inspection_level="full-book-read"))

    def test_rejects_unsafe_primary_and_verification_urls(self):
        for field in ("url", "verification_url"):
            for value in ("http://example.org/a", "javascript:alert(1)",
                          "https://user:secret@example.org/a", "/local/file", "https://"):
                with self.subTest(field=field, value=value):
                    self.assert_rejected(self.changed_row(**{field: value}))

    def test_schema_member_type_errors_are_reported_as_invalid_catalogs(self):
        for data in (None, [], dict(self.catalog, resources=[None]),
                     dict(self.catalog, updated_at=None), self.changed_row(id=None),
                     self.changed_row(category=[]), self.changed_row(verified_at=None)):
            with self.subTest(data_type=type(data).__name__,
                              row=data.get("resources", [None])[0] if isinstance(data, dict) else None):
                self.assert_rejected(data)

    def test_starters_resolve_to_distinct_catalog_records(self):
        starters = self.catalog["starter_ids"]
        self.assertTrue(starters)
        self.assertEqual(len(starters), len(set(starters)))
        for value in (["missing-resource"], [starters[0], starters[0]]):
            with self.subTest(starter_ids=value):
                self.assert_rejected(dict(copy.deepcopy(self.catalog), starter_ids=value))

    def test_optional_website_catalog_matches_source(self):
        if not SITE.exists():
            self.skipTest("Website not included in this toolkit copy")
        published = json.loads(SITE.read_text(encoding="utf-8-sig"))
        self.assertEqual(published, self.catalog)


if __name__ == "__main__":
    unittest.main()
