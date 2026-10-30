"""Independent metadata-library regression and artifact checks (stdlib only)."""
from collections import Counter
from contextlib import redirect_stdout
import hashlib
from html.parser import HTMLParser
import importlib.util
import io
import json
from pathlib import Path
import random
import re
import sys
import tempfile
import types
import unittest
import unicodedata
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "paper-writing/scripts/collect_library.py"
spec = importlib.util.spec_from_file_location("independent_library", SCRIPT)
library = importlib.util.module_from_spec(spec)
spec.loader.exec_module(library)


def citation(n=1, year=2021, venue="CVPR"):
    return {"id": f"test-{n}", "title": f"An independent contribution {n}",
            "authors": ["Ada Example", "Bo Example"], "venue": venue, "year": year,
            "url": f"https://openaccess.thecvf.com/content/CVPR{year}/html/Example_{n}.html",
            "collection_level": "citation_metadata", "semantic_review_performed": False}


def medical(n=1):
    return dict(citation(n), venue="NEJM", journal_issn="0028-4793",
                url=f"https://europepmc.org/article/MED/{10000+n}",
                first_publication_date="2021-04-15", publication_types=["Journal Article"])


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


class IndexLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.href, self.parts = {}, None, []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href, self.parts = dict(attrs).get("href"), []

    def handle_data(self, value):
        if self.href:
            self.parts.append(value)

    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            self.links[self.href] = " ".join(self.parts)
            self.href = None


class LibrarySyntheticTests(unittest.TestCase):
    def test_valid_citation_and_medical_metadata(self):
        library.validate_record(citation())
        library.validate_record(medical())

    def test_cutoff_year_type_and_authors(self):
        for key, value in (("year", 2023), ("year", True), ("year", "2022"),
                           ("authors", []), ("authors", [""]), ("authors", "Ada Example")):
            row = citation()
            row[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                library.validate_record(row)

    def test_medical_exact_issn_and_first_publication_cutoff(self):
        for key, value in (("journal_issn", "0000-0000"),
                           ("journal_issn", "1538-3598"),
                           ("first_publication_date", "2023-01-01"),
                           ("first_publication_date", "2021-02-30"),
                           ("url", "https://unrelated.example/article/123")):
            row = medical()
            row[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                library.validate_record(row)

    def test_official_host_and_main_conference_scope(self):
        for venue, year, url in (
            ("CVPR", 2021, "https://openaccess.thecvf.com.attacker.example/content/CVPR2021/html/X.html"),
            ("CVPR", 2021, "https://openaccess.thecvf.com/content/CVPR2021_workshops/html/X.html"),
            ("CVPR", 2021, "https://openaccess.thecvf.com/content/CVPR2021W/html/X.html"),
            ("NeurIPS", 2022, "https://proceedings.neurips.cc/paper_files/paper/2022/hash/abc-Abstract-Datasets_and_Benchmarks.html"),
        ):
            row = dict(citation(), venue=venue, year=year, url=url)
            with self.subTest(url=url), self.assertRaises(ValueError):
                library.validate_record(row)

    def test_metadata_conversion_drops_article_text_and_host_paths(self):
        raw = dict(citation(), abstract="An abstract.", full_text="Article body.",
                   full_text_local_path="fixtures/private/body.pdf", abstractText="Upstream text.",
                   introduction_extracted="Opening prose.", body="Secret source body.")
        row = library.metadata(raw)
        self.assertTrue(set(row).isdisjoint({"abstract", "full_text", "full_text_local_path",
                                           "abstractText", "introduction_extracted", "body"}))
        self.assertEqual(row["collection_level"], "citation_metadata")
        self.assertIs(row["semantic_review_performed"], False)
        library.validate_record(row)
        for key in ("abstract", "abstractText", "body", "full_text", "full_text_local_path",
                    "introduction_extracted", "source_pdf_local_path"):
            changed = dict(row, **{key: "Leaked content."})
            with self.subTest(key=key), self.assertRaises(ValueError):
                library.validate_record(changed)

    def test_id_title_doi_and_canonical_url_duplicates_rejected(self):
        for identity in ("id", "title", "doi", "url"):
            first, second = citation(1), citation(2)
            if identity == "title":
                first["title"], second["title"] = "A Method: Two Tasks!", "a method two tasks"
            elif identity == "doi":
                first["doi"], second["doi"] = "https://doi.org/10.1234/ABC", "doi:10.1234/abc"
            elif identity == "url":
                second["url"] = first["url"].replace("https:", "http:") + "#abstract"
            else:
                second["id"] = first["id"]
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                library.validate_rows([first, second], expected=2)

    def test_declared_venue_quotas_cannot_be_replaced_by_aggregate_count(self):
        with self.assertRaises(ValueError):
            library.validate_rows([citation(1), citation(2)], expected=2,
                                  quotas={"CVPR": 1, "ICCV": 1})

    def test_selection_preserves_seed_identity_and_balances_available_years(self):
        candidates = [citation(n, year) for year in (2020, 2021, 2022)
                      for n in range(year * 10, year * 10 + 5)]
        seed = candidates[0]
        selected, rejected = library.select(candidates, {seed["id"]}, quotas={"CVPR": 7})
        self.assertFalse(rejected)
        self.assertEqual(len(selected), 7)
        self.assertEqual(sorted(Counter(r["year"] for r in selected).values()), [2, 2, 3])
        kept = next(r for r in selected if r["id"] == seed["id"])
        for field in ("id", "title", "year", "venue", "url"):
            self.assertEqual(kept[field], seed[field])
        self.assertIs(kept["retained_from_initial_300"], True)
        random.Random(2022).shuffle(candidates)
        again, _ = library.select(candidates, {seed["id"]}, quotas={"CVPR": 7})
        self.assertEqual(selected, again)

    def test_selection_missing_seed_duplicate_seed_or_short_pool_fails(self):
        for candidates, seeds, quota in (
            ([citation(1)], {"absent"}, 1),
            ([citation(1)], set(), 2),
            ([citation(1), dict(citation(2), title=citation(1)["title"])], {"test-1", "test-2"}, 2),
        ):
            with self.subTest(seeds=seeds, quota=quota), self.assertRaises(ValueError):
                library.select(candidates, seeds, quotas={"CVPR": quota})

    def test_medical_author_helper_preserves_distinct_people_with_same_display_name(self):
        # Isolate the pure parser while keeping this suite stdlib-only. The
        # network dependency is never called or required for this fixture.
        script = ROOT / "paper-writing/scripts/collect_library_medical.py"
        parser_spec = importlib.util.spec_from_file_location("independent_medical_authors", script)
        parser = importlib.util.module_from_spec(parser_spec)
        with patch.dict(sys.modules, {"requests": types.ModuleType("requests")}):
            parser_spec.loader.exec_module(parser)
        raw = {"authorList": {"author": [
            {"fullName": "Wang J", "authorId": "person-one"},
            {"fullName": "Wang J", "authorId": "person-two"},
            {"collectiveName": "Trial Investigators"},
        ]}}
        self.assertEqual(parser.authors_from_core(raw), ["Wang J", "Wang J", "Trial Investigators"])

    def test_collect_worker_arguments_use_supported_options_and_given_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "library"
            seed = Path(directory) / "original.jsonl"
            rows = [dict(citation(n), id=f"seed-{n}") for n in range(300)]
            with patch.object(sys, "argv", [str(SCRIPT), "--output-root", str(root),
                                            "--seed", str(seed), "--collect"]), \
                 patch.object(library, "load_rows", side_effect=[rows, [], [], []]), \
                 patch.object(library, "select", return_value=(rows, [])), \
                 patch.object(library, "validate_rows"), \
                 patch.object(library.subprocess, "run") as run:
                with redirect_stdout(io.StringIO()):
                    library.main()
            commands = {Path(call.args[0][1]).stem: call.args[0] for call in run.call_args_list}
            self.assertEqual(set(commands), {"collect_library_cv", "collect_library_ml", "collect_library_medical"})
            for name, seed_flag in (("cv", "--seed-file"), ("ml", "--legacy"), ("medical", "--seed")):
                command = commands[f"collect_library_{name}"]
                output_flag = "--out-dir"
                self.assertIn(output_flag, command)
                self.assertIn(seed_flag, command)
                self.assertEqual(command[command.index(seed_flag) + 1], str(seed))
                self.assertEqual(Path(command[command.index(output_flag) + 1]), root / "shards")


class LibraryArtifactTests(unittest.TestCase):
    def test_optional_offline_source_caches_and_iclr_index_author_fidelity(self):
        folder = ROOT / "research/library-10000"
        if not (folder / "papers.jsonl").is_file() or not (folder / "shards/ml-cache").is_dir():
            self.skipTest("Local raw source caches are not present in this export.")
        sources = {}
        for meta in (folder / "shards/ml-cache").glob("*.json"):
            record = json.loads(meta.read_text(encoding="utf-8"))
            data = meta.with_suffix(".response").read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), record["response_sha256"])
            sources[record["url"]] = data.decode("utf-8-sig")
        self.assertTrue(sources)
        for path in (folder / "shards/.cv-cache").glob("*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(hashlib.sha256(record["html"].encode()).hexdigest(), record["response_sha256"])
        rows = read_rows(folder / "papers.jsonl")
        normalize = lambda value: re.sub(r"[^\w]+", "", unicodedata.normalize("NFKC", value).casefold())
        for year in (2021, 2022):
            page = IndexLinks()
            page.feed(sources[f"https://iclr.cc/virtual/{year}/papers.html"])
            index = {f"https://iclr.cc{path}": title for path, title in page.links.items()
                     if re.fullmatch(fr"/virtual/{year}/poster/\d+", path)}
            bulk = json.loads(next(data for url, data in sources.items()
                                   if str(year) in url and "orals-posters.json" in url))
            posters = {f"https://iclr.cc/virtual/{year}/poster/{r['id']}": r
                       for r in bulk["results"] if r.get("eventtype") == "Poster"}
            checked = 0
            for row in rows:
                if row["venue"] == "ICLR" and row["year"] == year:
                    self.assertIn(row["url"], index)
                    self.assertEqual(normalize(row["title"]), normalize(index[row["url"]]))
                    expected = [" ".join(a["fullname"].split()) for a in posters[row["url"]]["authors"]
                                if a["fullname"].strip()]
                    self.assertEqual(row["authors"], expected)
                    checked += 1
            self.assertEqual(checked, 500)
        bulk2020 = json.loads(sources["https://iclr.cc/virtual_2020/papers.json"])
        authors2020 = {normalize(r["content"]["title"]): [" ".join(a.split()) for a in r["content"]["authors"]
                                                         if a.strip()] for r in bulk2020}
        checked = 0
        for row in rows:
            if row["venue"] == "ICLR" and row["year"] == 2020:
                self.assertEqual(row["authors"], authors2020[normalize(row["title"])])
                checked += 1
        self.assertEqual(checked, 500)
        medical_cache = folder / "shards/medical-cache"
        if medical_cache.is_dir():
            indexed = {}
            for path in medical_cache.glob("*.json"):
                record = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(record.get("author_occurrence_policy"),
                                 "preserve-ordered-core-authorList-occurrences-v2")
                indexed.update({r["id"]: r for r in record.get("eligible_citation_metadata", [])})
            checked = 0
            for row in rows:
                if row["venue"] in {"NEJM", "The Lancet", "JAMA", "BMJ", "Nature Medicine", "Nature"}:
                    self.assertIn(row["id"], indexed)
                    self.assertEqual(row["authors"], indexed[row["id"]]["authors"])
                    checked += 1
            self.assertEqual(checked, 1000)

    def test_final_registry_count_quotas_identity_and_summary_hash(self):
        folder = ROOT / "research/library-10000"
        if not (folder / "papers.jsonl").is_file():
            self.skipTest("Final registry is still being assembled; synthetic checks remain available.")
        rows = read_rows(folder / "papers.jsonl")
        library.validate_rows(rows, quotas=library.QUOTAS)
        self.assertEqual(Counter(r["venue"] for r in rows), Counter({
            "CVPR": 2500, "ICCV": 1000, "NeurIPS": 2000, "ICML": 2000, "ICLR": 1500,
            "NEJM": 200, "The Lancet": 200, "JAMA": 200, "BMJ": 200,
            "Nature Medicine": 100, "Nature": 100,
        }))
        for venue in {r["venue"] for r in rows}:
            counts = Counter(r["year"] for r in rows if r["venue"] == venue)
            self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)
        self.assertTrue(all(not any(key.endswith("_local_path") or key in {
            "abstract", "abstractText", "body", "full_text", "introduction_extracted"} for key in r) for r in rows))
        seed_path = ROOT / "research/historical-2022/papers.jsonl"
        if not seed_path.is_file():
            self.skipTest("Historical seed artifact is not present in this export.")
        seed = read_rows(seed_path)
        selected = {r["id"]: r for r in rows}
        self.assertEqual(len(seed), 300)
        self.assertTrue({r["id"] for r in seed}.issubset(selected))
        for prior in seed:
            current = selected[prior["id"]]
            self.assertEqual(library.title_key(current["title"]), library.title_key(prior["title"]))
            self.assertEqual(current["year"], prior["year"])
            expected_venue = "NEJM" if prior["venue"] == "New England Journal of Medicine" else prior["venue"]
            self.assertEqual(current["venue"], expected_venue)
            self.assertIs(current["retained_from_initial_300"], True)
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["counts"], dict(Counter(r["venue"] for r in rows)))
        self.assertEqual(summary["total_records"], 10000)
        self.assertEqual(summary["corpus_sha256"], hashlib.sha256((folder / "papers.jsonl").read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
