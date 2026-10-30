#!/usr/bin/env python3
"""Collect 1,200 citation-only medical candidates (1,000 quota + 20% reserves).

Uses the official Europe PMC core search API, exact flagship ISSNs, and fixed
2018--2022 journal/year strata. Core abstracts are used in memory to apply the
historical collector's article-eligibility filter, then discarded. No article
body endpoint is called; local caches contain sanitized citation metadata only.
Requires requests. This is a convenience collection, not a systematic review.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
import json
import math
from pathlib import Path
import re
import threading
import time

import requests


API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
DOCUMENTATION = "https://dev.europepmc.org/RestfulWebService"
CUTOFF = date(2022, 12, 31)
YEARS = tuple(range(2018, 2023))
JOURNALS = (
    ("NEJM", "0028-4793", 200),
    ("The Lancet", "0140-6736", 200),
    ("JAMA", "0098-7484", 200),
    ("BMJ", "0959-8138", 200),
    ("Nature Medicine", "1078-8956", 100),
    ("Nature", "0028-0836", 100),
)
EXCLUDED_TYPES = {
    "editorial", "letter", "comment", "published erratum", "correction", "news",
    "historical article", "biography", "retracted publication", "retraction of publication",
    "expression of concern", "clinical trial protocol", "preprint", "congress",
    "interview", "personal narrative",
}
EXCLUDED_TITLES = re.compile(
    r"^(?:correction(?:s)?|erratum|author correction|publisher correction|retraction|"
    r"expression of concern)\b|\bstudy protocol\b|\bprotocol for\b", re.I,
)
SCHEMA = "medical-citation-candidates-v1"
AUTHOR_POLICY = "preserve-ordered-core-authorList-occurrences-v2"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))).strip()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8", newline="\n")


def authors_from_core(raw):
    names = []
    for item in raw.get("authorList", {}).get("author", []):
        name = clean(item.get("fullName") or item.get("collectiveName") or
                     " ".join(filter(None, (item.get("lastName"), item.get("firstName")))))
        # Identical abbreviated display names may denote different people.
        # Preserve every ordered authorList occurrence supplied by the API.
        if name:
            names.append(name)
    if not names and clean(raw.get("authorString")):
        names = [clean(part) for part in raw["authorString"].split(",") if clean(part)]
    return names


def reject_type(title, publication_types):
    lower = {item.lower() for item in publication_types}
    if lower & EXCLUDED_TYPES or EXCLUDED_TITLES.search(title):
        return "excluded_type_or_protocol_title"
    if "review" in lower and not ({"systematic review", "meta-analysis"} & lower or
                                  re.search(r"systematic review|meta.analysis", title, re.I)):
        return "narrative_review"
    if "journal article" not in lower and not (lower & {"systematic review", "meta-analysis"}):
        return "not_article_or_systematic_review"
    return None


def convert_core(raw, venue, issn, year, query, accessed_date):
    journal = raw.get("journalInfo", {}).get("journal", {})
    if issn not in (journal.get("issn"), journal.get("essn")):
        return None, "journal_issn_mismatch"
    if raw.get("source") != "MED" or not str(raw.get("id", "")).isdigit():
        return None, "not_pubmed_record"
    try:
        pubyear = int(raw.get("pubYear", "0"))
        firstdate = date.fromisoformat(raw.get("firstPublicationDate", ""))
    except (ValueError, TypeError):
        return None, "missing_valid_year_or_date"
    if pubyear != year or firstdate.year != year or firstdate > CUTOFF:
        return None, "outside_stratum_or_cutoff"
    title = clean(raw.get("title"))
    types = raw.get("pubTypeList", {}).get("pubType", [])
    if not isinstance(types, list):
        types = [str(types)]
    rejected = reject_type(title, types)
    if rejected:
        return None, rejected
    # Same bounded eligibility rule as collect_historical_medical.py; the text is
    # neither persisted in cache nor represented as semantically inspected.
    if len(clean(raw.get("abstractText")).split()) < 70:
        return None, "abstract_under_70_words"
    authors = authors_from_core(raw)
    if not title or not authors:
        return None, "missing_title_or_authors"
    pmid = str(raw["id"])
    return {
        "id": "med-" + pmid, "title": title, "authors": authors,
        "venue": venue, "year": pubyear, "url": f"https://europepmc.org/article/MED/{pmid}",
        "doi": clean(raw.get("doi")).lower() or None, "pmid": pmid, "pmcid": raw.get("pmcid"),
        "journal_issn": issn, "issn": issn, "source_journal_title": journal.get("title"),
        "publication_types": types, "first_publication_date": firstdate.isoformat(),
        "source_api": API, "source_query": query, "accessed_date": accessed_date,
        "collection_level": "citation_metadata", "semantic_review_performed": False,
        "selection_method": "Exact-journal/year convenience strata; 2018-2022 only; journal articles or systematic reviews/meta-analyses passing the historical eligibility filter; no probability-sampling claim.",
    }, None


class Client:
    def __init__(self, cache, log, refresh=False, timeout=35):
        self.cache, self.log, self.refresh, self.timeout = cache, log, refresh, timeout
        self.lock = threading.Lock()
        self.next_request = 0.0
        self.host_backoff = 0.0

    def record(self, event):
        with self.lock:
            self.log.append(event)

    def throttle(self):
        # At most two starts/second, with a shared host-wide 429 backoff. The
        # executor also permits at most two requests in flight to this host.
        while True:
            with self.lock:
                now = time.monotonic()
                delay = max(self.next_request, self.host_backoff) - now
                if delay <= 0:
                    self.next_request = now + 0.5
                    return
            time.sleep(min(delay, 1.0))

    @staticmethod
    def retry_after(response):
        value = response.headers.get("Retry-After", "")
        try:
            return max(0, float(value))
        except ValueError:
            try:
                return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError, OverflowError):
                return 2.0

    def page(self, venue, issn, year, query, cursor, page_size):
        params = {"query": query, "format": "json", "resultType": "core",
                  "pageSize": page_size, "cursorMark": cursor}
        key = hashlib.sha256(json.dumps([SCHEMA, venue, issn, year, params], sort_keys=True).encode()).hexdigest()
        cache_path = self.cache / (key + ".json")
        if cache_path.is_file() and not self.refresh:
            result = json.loads(cache_path.read_text(encoding="utf-8"))
            if result.get("author_occurrence_policy") == AUTHOR_POLICY:
                self.record({"event": "cache_hit", "venue": venue, "year": year,
                             "cache_key": key, "source_api": API, "source_query": query,
                             "source_url": result.get("source_url"), "original_fetched_at_utc": result.get("fetched_at_utc"),
                             "original_response_sha256": result.get("response_sha256")})
                return result
            self.record({"event": "cache_invalidated", "venue": venue, "year": year,
                         "cache_key": key, "reason": "Author occurrences require a fresh core API response"})
        for attempt in range(4):
            self.throttle()
            started = utc_now()
            try:
                response = requests.get(API, params=params, timeout=self.timeout,
                                        headers={"User-Agent": "PaperWritingCitationLibrary/1.0 (metadata-only research collection)"})
                self.record({"event": "request", "venue": venue, "year": year, "attempt": attempt + 1,
                             "started_utc": started, "completed_utc": utc_now(), "status_code": response.status_code,
                             "source_url": response.url, "response_bytes": len(response.content),
                             "response_sha256": hashlib.sha256(response.content).hexdigest()})
                if response.status_code == 429:
                    seconds = self.retry_after(response)
                    with self.lock:
                        self.host_backoff = max(self.host_backoff, time.monotonic() + seconds)
                    self.record({"event": "retry_after", "status_code": 429, "delay_seconds": seconds,
                                 "venue": venue, "year": year})
                    if attempt == 3:
                        response.raise_for_status()
                    continue
                if response.status_code in {500, 502, 503, 504} and attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                response.raise_for_status()
                data = response.json()
                rows, reasons = [], Counter()
                for raw in data.get("resultList", {}).get("result", []):
                    row, reason = convert_core(raw, venue, issn, year, query, date.today().isoformat())
                    if row:
                        rows.append(row)
                    else:
                        reasons[reason] += 1
                result = {"schema": SCHEMA, "venue": venue, "year": year, "source_query": query,
                          "author_occurrence_policy": AUTHOR_POLICY,
                          "source_api": API, "source_url": response.url, "hit_count": data.get("hitCount"),
                          "fetched_at_utc": utc_now(), "response_sha256": hashlib.sha256(response.content).hexdigest(),
                          "response_bytes": len(response.content), "http_status_code": response.status_code,
                          "next_cursor": data.get("nextCursorMark"),
                          "raw_candidate_count": len(data.get("resultList", {}).get("result", [])),
                          "rejected_reasons": dict(reasons), "eligible_citation_metadata": rows,
                          "cache_note": "Sanitized citation metadata only. Core abstracts and body links were discarded; no article bodies requested."}
                write_json(cache_path, result)
                return result
            except (requests.RequestException, ValueError) as exc:
                self.record({"event": "request_error", "venue": venue, "year": year,
                             "attempt": attempt + 1, "error_type": type(exc).__name__})
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        raise RuntimeError("No response after bounded retries")


def query_for(venue, issn, year):
    query = (f"SRC:MED AND ISSN:{issn} AND PUB_YEAR:{year} AND "
             f"FIRST_PDATE:[{year}-01-01 TO {year}-12-31] AND HAS_ABSTRACT:y")
    if venue == "Nature":
        query += " AND (TITLE_ABS:patient* OR TITLE_ABS:clinical OR TITLE_ABS:disease OR TITLE_ABS:cancer)"
    return query + " sort_date:y"


def load_seeds(path, client, page_size):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    rows = [row for row in rows if row["id"].startswith("med-")]
    if len(rows) != 50 or len({row["id"] for row in rows}) != 50:
        raise ValueError("Expected exactly 50 stable medical IDs in the historical seed registry")
    seeds = {}
    alias = {"New England Journal of Medicine": "NEJM"}
    for raw in rows:
        venue = alias.get(raw["venue"], raw["venue"])
        issn = next(issn for journal, issn, quota in JOURNALS if journal == venue)
        year = int(raw["year"])
        firstdate = date.fromisoformat(raw["first_publication_date"])
        if year not in YEARS or firstdate.year != year or firstdate > CUTOFF or raw.get("journal_issn") != issn:
            raise ValueError("Seed does not meet exact journal/year/cutoff constraints: " + raw["id"])
        reason = reject_type(raw["title"], raw.get("publication_types", []))
        if reason:
            raise ValueError("Historical seed fails article-type eligibility: " + raw["id"])
        if not raw.get("authors"):
            query = f"EXT_ID:{raw['pmid']} AND SRC:MED"
            result = client.page(venue, issn, year, query, "*", 1)
            matches = [row for row in result["eligible_citation_metadata"] if row["id"] == raw["id"]]
            if not matches:
                raise ValueError("Cannot repair the empty author list for historical seed: " + raw["id"])
            row = matches[0]
            client.record({"event": "seed_authors_repaired", "id": row["id"], "author_count": len(row["authors"])})
        else:
            row = {key: raw.get(key) for key in (
                "id", "title", "authors", "year", "url", "doi", "pmid", "pmcid", "source_journal_title",
                "first_publication_date", "publication_types", "source_api", "source_query", "accessed_date")}
            row.update(venue=venue, journal_issn=issn, issn=issn, collection_level="citation_metadata",
                       semantic_review_performed=False, selection_method="Historical exact-journal/year seed retained with stable ID; abstracts and body paths removed.")
        row["historical_seed"] = True
        seeds.setdefault((venue, year), []).append(row)
    return seeds


def collect_stratum(client, venue, issn, year, quota, seeds, page_size, max_pages):
    query = query_for(venue, issn, year)
    candidates = {row["id"]: row for row in seeds}
    cursor = "*"
    rejected = Counter()
    fetched = 0
    required_seed_ids = {row["id"] for row in seeds}
    refreshed_seed_ids = set()
    for page_number in range(1, max_pages + 1):
        result = client.page(venue, issn, year, query, cursor, page_size)
        fetched += result["raw_candidate_count"]
        rejected.update(result["rejected_reasons"])
        for row in result["eligible_citation_metadata"]:
            if row["id"] in required_seed_ids:
                row = dict(row)
                row["historical_seed"] = True
                row["historical_seed_metadata_refreshed"] = True
                candidates[row["id"]] = row
                refreshed_seed_ids.add(row["id"])
            else:
                candidates.setdefault(row["id"], row)
        if ((len(candidates) >= quota and required_seed_ids <= refreshed_seed_ids) or
                not result.get("next_cursor") or result["next_cursor"] == cursor):
            break
        cursor = result["next_cursor"]
    if required_seed_ids - refreshed_seed_ids:
        raise RuntimeError(f"Historical seed metadata not refreshed in bounded {venue} {year} API pages: " +
                           ", ".join(sorted(required_seed_ids - refreshed_seed_ids)))
    chosen = sorted(candidates.values(), key=lambda row: (not row.get("historical_seed", False), row["first_publication_date"], int(row["pmid"])))[:quota]
    for rank, row in enumerate(chosen, 1):
        row["selection_rank_within_stratum"] = rank
        row["candidate_stratum_quota"] = quota
    log = {"event": "stratum_selection", "venue": venue, "issn": issn, "year": year,
           "source_query": query, "api_hit_count": result.get("hit_count"), "pages_processed": page_number,
           "fetched_candidate_count": fetched, "eligible_count": len(candidates), "selected_count": len(chosen),
           "target_with_reserves": quota, "historical_seed_count": len(seeds), "rejected_reasons": dict(rejected)}
    log["historical_seed_metadata_refreshed_count"] = len(refreshed_seed_ids)
    client.record(log)
    print(f"{venue} {year}: {len(chosen)}/{quota} candidates, {len(seeds)} retained seeds", flush=True)
    if len(chosen) != quota:
        raise RuntimeError(f"Insufficient eligible candidates in {venue} {year}: {len(chosen)} < {quota}")
    return chosen, log


def validate(records, seed_ids):
    if len(records) != len({row["id"] for row in records}):
        raise ValueError("Duplicate IDs in medical candidate shard")
    if not seed_ids <= {row["id"] for row in records}:
        raise ValueError("A historical medical seed ID was dropped")
    for row in records:
        if not isinstance(row.get("authors"), list) or not row["authors"] or not all(isinstance(name, str) and name.strip() for name in row["authors"]):
            raise ValueError("Empty or invalid author list: " + row["id"])
        if row["collection_level"] != "citation_metadata" or row["semantic_review_performed"] is not False:
            raise ValueError("Incorrect evidence-level declaration")
        if any("abstract" == key or key.endswith("_local_path") or key in {"full_text", "body", "abstractText"} for key in row):
            raise ValueError("Article text or host path leaked into metadata")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--output-root", type=Path, help="The library-10000 directory; writes into its shards directory")
    destination.add_argument("--out-dir", type=Path, help="Exact shard output directory; compatible with the library orchestrator")
    parser.add_argument("--seed", type=Path, help="Historical papers.jsonl; defaults to sibling historical-2022/papers.jsonl")
    parser.add_argument("--reserve-fraction", type=float, default=0.2)
    parser.add_argument("--page-size", type=int, default=250)
    parser.add_argument("--max-pages", type=int, default=6)
    parser.add_argument("--refresh", action="store_true", help="Refresh sanitized metadata caches")
    args = parser.parse_args()
    if not 0 <= args.reserve_fraction <= 1 or not 1 <= args.page_size <= 1000 or not 1 <= args.max_pages <= 20:
        parser.error("Invalid reserve fraction, page size or bounded page count")
    if args.out_dir:
        shards = args.out_dir.resolve()
        root = shards.parent
    else:
        root = args.output_root.resolve()
        shards = root / "shards"
    shards.mkdir(parents=True, exist_ok=True)
    provenance_path = shards / "medical-provenance.jsonl"
    log = [json.loads(line) for line in provenance_path.read_text(encoding="utf-8").splitlines() if line.strip()] if provenance_path.is_file() else []
    log.append({"event": "collection_started", "timestamp_utc": utc_now(), "schema": SCHEMA,
            "source_api": API, "official_documentation": DOCUMENTATION,
            "max_concurrent_requests_per_host": 2, "max_request_starts_per_second": 2,
            "max_attempts_per_request": 4, "retry_after_respected": True,
            "cutoff": CUTOFF.isoformat(), "reserve_fraction": args.reserve_fraction,
            "collection_level": "citation_metadata", "article_body_requests": 0,
            "cache_contents": "Sanitized eligible citations and provenance only; no abstracts or article bodies"})
    client = Client(shards / "medical-cache", log, args.refresh)
    try:
        seed_path = args.seed or root.parent / "historical-2022" / "papers.jsonl"
        seeds = load_seeds(seed_path, client, args.page_size)
        records, strata = [], []
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(collect_stratum, client, venue, issn, year,
                                   math.ceil(total * (1 + args.reserve_fraction) / len(YEARS)),
                                   seeds.get((venue, year), []), args.page_size, args.max_pages)
                       for venue, issn, total in JOURNALS for year in YEARS]
            for future in as_completed(futures):
                rows, stratum = future.result()
                records.extend(rows)
                strata.append(stratum)
        seed_ids = {row["id"] for group in seeds.values() for row in group}
        validate(records, seed_ids)
        records.sort(key=lambda row: (row["venue"], row["year"], row["selection_rank_within_stratum"], row["id"]))
        output = shards / "medical-candidates.jsonl"
        write_jsonl(output, records)
        summary = {"schema": SCHEMA, "record_count": len(records), "unique_ids": len({row["id"] for row in records}),
                   "quota_before_reserves": 1000, "reserve_fraction": args.reserve_fraction,
                   "historical_seed_ids_preserved": len(seed_ids), "cutoff": CUTOFF.isoformat(),
                   "venues": dict(sorted(Counter(row["venue"] for row in records).items())),
                   "years": dict(sorted(Counter(row["year"] for row in records).items())),
                   "strata": sorted(strata, key=lambda row: (row["venue"], row["year"])),
                   "source_api": API, "official_documentation": DOCUMENTATION,
                   "collection_level": "citation_metadata", "semantic_reviews_claimed": 0,
                   "author_occurrence_policy": AUTHOR_POLICY,
                   "historical_seed_metadata_refreshed_count": sum(bool(row.get("historical_seed_metadata_refreshed")) for row in records),
                   "local_abstracts": 0, "article_body_requests": 0, "local_article_bodies": 0,
                   "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                   "validation": "passed", "author_lists_nonempty": True,
                   "selection_limits": ["Fixed journal and year convenience strata, not systematic or representative coverage.",
                                        "Nature restricted to health-related title/abstract query terms.",
                                        "Eligibility uses publication types, title filters and >=70-word abstracts in memory; no semantic article review.",
                                        "Source article abstracts and bodies are not persisted or redistributed."]}
        write_json(shards / "medical-summary.json", summary)
        log.append({"event": "collection_completed", "timestamp_utc": utc_now(), "record_count": len(records), "validation": "passed"})
        print(json.dumps({key: summary[key] for key in ("record_count", "historical_seed_ids_preserved", "venues", "years", "validation")}, ensure_ascii=False, sort_keys=True), flush=True)
    finally:
        write_jsonl(shards / "medical-provenance.jsonl", log)


if __name__ == "__main__":
    main()
