#!/usr/bin/env python3
"""Collect, select and validate 10,000 historical citation records.

The earlier 300-paper inspection collection stays separate. No article bodies or
abstracts are included in this metadata library, and collection is not reading.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import unicodedata
from urllib.parse import urlsplit, urlunsplit

QUOTAS = {"CVPR": 2500, "ICCV": 1000, "NeurIPS": 2000, "ICML": 2000,
          "ICLR": 1500, "NEJM": 200, "The Lancet": 200, "JAMA": 200,
          "BMJ": 200, "Nature Medicine": 100, "Nature": 100}
ISSNS = {"NEJM": {"0028-4793", "1533-4406"}, "The Lancet": {"0140-6736", "1474-547X"},
         "JAMA": {"0098-7484", "1538-3598"}, "BMJ": {"0959-8138", "1756-1833", "1468-5833"},
         "Nature Medicine": {"1078-8956", "1546-170X"}, "Nature": {"0028-0836", "1476-4687"}}
HOSTS = {"CVPR": {"openaccess.thecvf.com"}, "ICCV": {"openaccess.thecvf.com"},
         "NeurIPS": {"proceedings.neurips.cc", "papers.nips.cc"},
         "ICML": {"proceedings.mlr.press"}, "ICLR": {"iclr.cc", "openreview.net"}}
FIELDS = {"id", "title", "authors", "venue", "year", "url", "doi", "pmid", "pmcid",
          "journal_issn", "source_journal_title", "first_publication_date", "publication_types",
          "accessed_date", "source_listing_url", "source_system", "source_api", "source_query",
          "source_record_id", "selection_method", "source_sha256"}


def load_rows(path):
    return [json.loads(s) for s in Path(path).read_text(encoding="utf-8-sig").splitlines() if s.strip()]


def title_key(text):
    return re.sub(r"[^\w]+", "", unicodedata.normalize("NFKC", text).casefold())


def url_key(text):
    u = urlsplit(text)
    return urlunsplit(("https", u.netloc.lower(), u.path.rstrip("/"), u.query, ""))


def doi_key(text):
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", text.strip(), flags=re.I).casefold()


def identities(row):
    result = [("id", row["id"]), ("url", url_key(row["url"])), ("title", title_key(row["title"]))]
    if row.get("doi"):
        result.append(("doi", doi_key(row["doi"])))
    return result


def metadata(raw):
    row = {key: value for key, value in raw.items() if key in FIELDS}
    row.update(collection_level="citation_metadata", semantic_review_performed=False)
    if "source_listing_url" not in row:
        source = raw.get("selection_source_url") or raw.get("listing_url") or raw.get("source_url")
        if source:
            row["source_listing_url"] = source
    return row


def validate_record(row):
    allowed = FIELDS | {"collection_level", "semantic_review_performed", "retained_from_initial_300", "library_selection_method"}
    if not isinstance(row, dict) or set(row) - allowed:
        raise ValueError("Unexpected fields are not part of the public citation metadata schema")
    for key in ("id", "title", "venue", "url"):
        if not isinstance(row.get(key), str) or not row[key].strip():
            raise ValueError(f"Missing nonempty {key}")
    venue = row["venue"]
    if venue not in QUOTAS or type(row.get("year")) is not int or not 1900 <= row["year"] <= 2022:
        raise ValueError("Venue or publication year outside allowed scope")
    if not isinstance(row.get("authors"), list) or not row["authors"] or not all(
            isinstance(a, str) and a.strip() for a in row["authors"]):
        raise ValueError("Nonempty author list required")
    u = urlsplit(row["url"])
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password:
        raise ValueError("Invalid source URL")
    if "workshop" in row["url"].lower():
        raise ValueError("Workshop sources are excluded")
    if venue in HOSTS and u.hostname.lower() not in HOSTS[venue]:
        raise ValueError("Conference source must be an official proceedings/conference host")
    year = row["year"]
    if venue in {"CVPR", "ICCV"} and not re.fullmatch(
            rf"/content(?:_|/){venue}_?{year}/html/[^/]+\.html", u.path):
        raise ValueError("CVF source must be the exact main-conference/year paper path")
    if venue == "NeurIPS":
        suffix = "-Abstract-Conference.html" if year >= 2022 else "-Abstract.html"
        if not re.fullmatch(rf"/(?:paper|paper_files/paper)/{year}/hash/[a-f0-9]+{re.escape(suffix)}", u.path):
            raise ValueError("NeurIPS source must be the main-conference abstract track")
    if venue == "ICML" and year in {2020, 2021, 2022}:
        volume = {2020: 119, 2021: 139, 2022: 162}[year]
        if not re.fullmatch(rf"/v{volume}/[^/]+\.html", u.path):
            raise ValueError("ICML source must match its official year/volume")
    if venue in ISSNS:
        actual = set(re.findall(r"\d{4}-[\dXx]{4}", json.dumps(row.get("journal_issn", ""))))
        if not actual.intersection(ISSNS[venue]):
            raise ValueError("Exact medical journal ISSN is required")
        first = date.fromisoformat(row.get("first_publication_date", ""))
        if not date(1900, 1, 1) <= first <= date(2022, 12, 31):
            raise ValueError("Medical first-publication date outside cutoff")
        if u.hostname not in {"europepmc.org", "www.europepmc.org", "pubmed.ncbi.nlm.nih.gov"}:
            raise ValueError("Medical citation must link to its indexed source record")
    if row.get("collection_level") != "citation_metadata" or row.get("semantic_review_performed") is not False:
        raise ValueError("Current collection must be honestly labelled metadata only")
    if any(k in row for k in ("abstract", "full_text", "full_text_local_path", "introduction_extracted")):
        raise ValueError("Article text and local body paths are not public metadata")


def validate_rows(rows, expected=10000, quotas=None):
    if len(rows) != expected:
        raise ValueError(f"Expected {expected} records, received {len(rows)}")
    seen = set()
    for row in rows:
        validate_record(row)
        keys = identities(row)
        if any(key in seen for key in keys):
            raise ValueError(f"Duplicate record identity: {row['id']}")
        seen.update(keys)
    if quotas is not None and Counter(r["venue"] for r in rows) != Counter(quotas):
        raise ValueError("Venue counts do not match the declared quotas")


def select(candidates, seed_ids, quotas=QUOTAS):
    valid, rejected = {}, []
    for raw in candidates:
        try:
            row = metadata(raw)
            validate_record(row)
            valid.setdefault(row["id"], row)
        except (ValueError, TypeError) as error:
            rejected.append({"id": raw.get("id"), "reason": str(error)})
    missing = sorted(set(seed_ids) - valid.keys())
    if missing:
        raise ValueError(f"Historical seed records missing/invalid: {missing}")
    selected, seen = [], set()

    def add(row, retained=False):
        keys = identities(row)
        if any(key in seen for key in keys):
            return False
        row = dict(row)
        row["retained_from_initial_300"] = retained
        row["library_selection_method"] = (
            "Preserved initial 300 citation identity; metadata refreshed from official source."
            if retained else "Fixed venue quota; balance publication-year counts, then ascending SHA-256 of canonical source URL.")
        selected.append(row)
        seen.update(keys)
        return True

    for sid in sorted(seed_ids):
        if not add(valid[sid], True):
            raise ValueError(f"Historical seed identity duplicates another seed: {sid}")
    for venue, quota in quotas.items():
        groups = defaultdict(list)
        for row in valid.values():
            if row["venue"] == venue and row["id"] not in seed_ids:
                groups[row["year"]].append(row)
        pools = {year: deque(sorted(items, key=lambda r: hashlib.sha256(url_key(r["url"]).encode()).hexdigest()))
                 for year, items in groups.items()}
        counts = Counter(r["year"] for r in selected if r["venue"] == venue)
        current = sum(counts.values())
        if current > quota:
            raise ValueError("Quota cannot exclude retained initial records")
        while current < quota:
            available = [year for year in pools if pools[year]]
            if not available:
                raise ValueError(f"Insufficient unique eligible {venue} records for quota {quota}")
            year = min(available, key=lambda y: (counts[y], y))
            if add(pools[year].popleft()):
                counts[year] += 1
                current += 1
    selected.sort(key=lambda r: (r["venue"].casefold(), r["year"], r["id"]))
    return selected, rejected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--seed", required=True, type=Path, help="Original 300-paper JSONL registry")
    parser.add_argument("--collect", action="store_true", help="Run the three bounded bulk collectors first")
    parser.add_argument("--validate", action="store_true", help="Validate existing merged registry without collection")
    args = parser.parse_args()
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    seed_ids = {r["id"] for r in load_rows(args.seed)}
    if len(seed_ids) != 300:
        raise ValueError("Seed registry must contain the original 300 unique IDs")
    if args.validate:
        rows = load_rows(root / "papers.jsonl")
    else:
        shards = root / "shards"
        if args.collect:
            def run(name):
                seed_flag = {"cv": "--seed-file", "ml": "--legacy", "medical": "--seed"}[name]
                subprocess.run([sys.executable, str(Path(__file__).with_name(f"collect_library_{name}.py")),
                                "--out-dir", str(shards), seed_flag, str(args.seed.resolve())], check=True)
            with ThreadPoolExecutor(max_workers=3) as pool:
                list(pool.map(run, ["cv", "ml", "medical"]))
        candidates = [r for name in ("cv", "ml", "medical") for r in load_rows(shards / f"{name}-candidates.jsonl")]
        rows, rejected = select(candidates, seed_ids)
        (root / "rejected-candidates.json").write_text(json.dumps(rejected, indent=2) + "\n", encoding="utf-8")
    validate_rows(rows, quotas=QUOTAS)
    if not seed_ids.issubset({r["id"] for r in rows}):
        raise ValueError("Initial collection identities were not preserved")
    registry = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
    (root / "papers.jsonl").write_text(registry, encoding="utf-8", newline="\n")
    summary = {"version": 1, "total_records": len(rows), "cutoff_year": 2022,
               "counts": dict(sorted(Counter(r["venue"] for r in rows).items())),
               "years": dict(sorted(Counter(str(r["year"]) for r in rows).items())),
               "venue_year_counts": {v: dict(sorted(Counter(str(r["year"]) for r in rows if r["venue"] == v).items())) for v in QUOTAS},
               "quotas": QUOTAS, "retained_initial_collection_records": 300,
               "distribution": "citation_metadata_only", "abstract_records": 0, "fulltext_downloaded": 0,
               "new_selected_section_inspections": 0, "complete_paper_scientific_reviews_claimed": 0,
               "original_300_selected_section_inspections": 18,
               "corpus_sha256": hashlib.sha256(registry.encode()).hexdigest(), "source_of_truth": "papers.jsonl",
               "validated_at": datetime.now(timezone.utc).isoformat(),
               "limits": ["Explicit venue/year-stratified convenience selection, not an objective ranking or representative sample.",
                          "Citation metadata collection is distinct from abstract reading, article download or scientific review.",
                          "The original 300-paper collection and its inspection notes remain separately documented."]}
    (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "validated", "total_records": len(rows), "counts": summary["counts"], "sha256": summary["corpus_sha256"]}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(f"Collection failed: {error}", file=sys.stderr)
        raise SystemExit(1)
