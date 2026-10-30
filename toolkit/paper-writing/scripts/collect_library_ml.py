#!/usr/bin/env python3
"""Collect pre-2023 main-conference ML citation metadata from official bulk listings.

No abstracts, paper bodies, PDFs, or semantic-review claims are emitted. Raw bulk
responses are cached locally for reproducibility. Run from the repository root:

  python output/paper-writing/scripts/collect_library_ml.py --out-dir output/research/library-10000/shards

The candidate pool contains all eligible records from 2020--2022; the parent
library builder selects its balanced venue quotas after cross-source deduplication.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import threading
import time
import unicodedata
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ACCESSED = "2026-10-30"
YEARS = (2020, 2021, 2022)
PMLR = {2020: 119, 2021: 139, 2022: 162}
TARGETS = {"NeurIPS": 2000, "ICML": 2000, "ICLR": 1500}
LOCK = threading.Lock()
HOST_LIMITS = defaultdict(lambda: threading.BoundedSemaphore(2))


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def title_key(value):
    return re.sub(r"\W+", "", unicodedata.normalize("NFKC", value).casefold())


def canonical_identity(url):
    # NeurIPS migrated its old /paper/Y/hash path without changing paper IDs.
    return url.rstrip("/").replace("proceedings.neurips.cc/paper/", "proceedings.neurips.cc/paper_files/paper/")


class Collector:
    def __init__(self, out_dir, refresh=False):
        self.out_dir = out_dir
        self.cache_dir = out_dir / "ml-cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.refresh = refresh
        self.events = []

    def log(self, **event):
        with LOCK:
            self.events.append({"time_utc": datetime.now(timezone.utc).isoformat(), **event})

    def fetch(self, url):
        key = sha(url.encode("utf-8"))
        raw_path = self.cache_dir / f"{key}.response"
        meta_path = self.cache_dir / f"{key}.json"
        if raw_path.exists() and meta_path.exists() and not self.refresh:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            data = raw_path.read_bytes()
            if meta.get("url") != url or sha(data) != meta.get("response_sha256"):
                raise RuntimeError(f"Cache integrity failure: {url}")
            self.log(event="cache_hit", **meta)
            if meta["status"] != 200:
                raise RuntimeError(f"Cached source HTTP {meta['status']}: {url}; use --refresh to retry")
            return data.decode("utf-8-sig")
        for attempt in (1, 2):
            try:
                with HOST_LIMITS[urlparse(url).netloc]:
                    response = requests.get(
                        url, timeout=(15, 60),
                        headers={"User-Agent": "HistoricalCitationMetadataLibrary/1.0 (bounded official-listing research)"},
                    )
                data = response.content
                meta = {
                    "url": url, "resolved_url": response.url, "status": response.status_code,
                    "response_bytes": len(data), "response_sha256": sha(data),
                    "content_type": response.headers.get("Content-Type", ""),
                    "cache_path": raw_path.relative_to(self.out_dir).as_posix(),
                    "accessed_date": ACCESSED,
                }
                self.log(event="network_response", attempt=attempt, **meta)
                raw_path.write_bytes(data)
                meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                if response.status_code in (401, 403, 404, 429):
                    raise RuntimeError(f"Source HTTP {response.status_code}: {url}; no retry for denial/missing/throttling")
                response.raise_for_status()
                return data.decode("utf-8-sig")
            except requests.RequestException as error:
                self.log(event="network_error", url=url, attempt=attempt, error=str(error))
                if attempt == 2:
                    raise
        raise RuntimeError(f"Source unavailable: {url}")

    def record(self, venue, year, title, authors, url, listing_url, system, **extra):
        authors = [clean(a) for a in authors if clean(a)]
        title = clean(title)
        if not title or not authors:
            raise ValueError(f"Missing required citation metadata: {venue} {year} {url}")
        return {
            "id": f"ml-{venue.lower()}-{year}-" + sha(url.encode("utf-8"))[:12],
            "title": title, "authors": authors, "venue": venue, "year": year,
            "url": url, "source_listing_url": listing_url, "source_system": system,
            "accessed_date": ACCESSED, "collection_level": "citation_metadata",
            "semantic_review_performed": False,
            "selection_method": "Complete official 2020--2022 main-conference bulk listing; candidate pool for balanced quota selection",
            **extra,
        }

    def neurips(self, year):
        listing = f"https://proceedings.neurips.cc/paper/{year}"
        soup = BeautifulSoup(self.fetch(listing), "html.parser")
        records = []
        excluded = 0
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if "-Abstract" not in href:
                continue
            if year == 2022 and not href.endswith("-Abstract-Conference.html"):
                excluded += 1
                continue
            parent = anchor.find_parent(class_="paper-content") or anchor.parent
            authors = parent.select_one(".paper-authors")
            if authors is None:
                raise ValueError(f"Unexpected NeurIPS listing structure: {year} {href}")
            records.append(self.record(
                "NeurIPS", year, anchor.get_text(" ", strip=True),
                authors.get_text(" ", strip=True).split(","), urljoin(listing, href),
                listing, "NeurIPS official proceedings", main_venue_evidence="Official proceedings main-conference listing" + ("; Conference track suffix only" if year == 2022 else ""),
            ))
        self.log(event="listing_parsed", venue="NeurIPS", year=year, source_url=listing, records=len(records), excluded_nonconference=excluded)
        return records

    def icml(self, year):
        listing = f"https://proceedings.mlr.press/v{PMLR[year]}/"
        soup = BeautifulSoup(self.fetch(listing), "html.parser")
        heading = clean(soup.get_text(" ", strip=True)[:1800])
        if "International Conference on Machine Learning" not in heading:
            raise ValueError(f"Unexpected PMLR volume identity: {listing}")
        records = []
        for paper in soup.select("div.paper"):
            anchor = next((a for a in paper.find_all("a", href=True) if a.get_text(strip=True) == "abs"), None)
            title = paper.select_one(".title")
            authors = paper.select_one(".authors")
            if anchor is None or title is None or authors is None:
                raise ValueError(f"Unexpected ICML listing structure: {year}")
            records.append(self.record(
                "ICML", year, title.get_text(" ", strip=True), authors.get_text(" ", strip=True).split(","),
                urljoin(listing, anchor["href"]), listing, "PMLR official ICML proceedings",
                main_venue_evidence=f"PMLR volume {PMLR[year]}: International Conference on Machine Learning",
            ))
        self.log(event="listing_parsed", venue="ICML", year=year, source_url=listing, records=len(records))
        return records

    def iclr(self, year):
        records = []
        if year == 2020:
            listing = "https://iclr.cc/virtual_2020/papers.json"
            items = json.loads(self.fetch(listing))
            for item in items:
                content = item["content"]
                paper_id = item["id"]
                records.append(self.record(
                    "ICLR", year, content["title"], content["authors"],
                    f"https://iclr.cc/virtual_2020/poster_{paper_id}.html", listing,
                    "ICLR official virtual conference", openreview_id=paper_id,
                    main_venue_evidence="Official ICLR 2020 accepted conference papers JSON",
                ))
        else:
            listing = f"https://iclr.cc/virtual/{year}/papers.html"
            html = self.fetch(listing)
            soup = BeautifulSoup(html, "html.parser")
            listed = {urljoin(listing, a["href"]): clean(a.get_text(" ", strip=True))
                      for a in soup.find_all("a", href=True)
                      if re.fullmatch(rf"/virtual/{year}/poster/\d+", a["href"])}
            # Discover the bulk URL from the actual official page, rather than
            # relying on a guessed endpoint or accessing every poster separately.
            match = re.search(r'start\("([^"]+orals-posters\.json)"', html)
            if not match:
                raise ValueError(f"ICLR bulk source link missing: {listing}")
            bulk_url = urljoin(listing, match.group(1))
            payload = json.loads(self.fetch(bulk_url))
            if payload.get("next"):
                raise ValueError(f"ICLR bulk source unexpectedly paginated: {bulk_url}")
            excluded = Counter()
            for item in payload["results"]:
                # Oral events duplicate their corresponding poster. This is the
                # same Poster-only filter used by ICLR's official papers UI.
                if item.get("eventtype") != "Poster":
                    excluded[item.get("eventtype", "unknown")] += 1
                    continue
                url = f"https://iclr.cc/virtual/{year}/poster/{item['id']}"
                if url not in listed or title_key(listed[url]) != title_key(clean(item["name"])):
                    raise ValueError(f"ICLR bulk record does not match official paper index: {url}")
                openreview_links = [em.get("uri", "") for em in item.get("eventmedia", []) if "openreview.net/forum?id=" in em.get("uri", "")]
                records.append(self.record(
                    "ICLR", year, item["name"], [a["fullname"] for a in item["authors"]],
                    url, listing, "ICLR official virtual conference", source_metadata_url=bulk_url,
                    main_venue_evidence="Poster paper in official conference papers index; matching bulk title and event ID",
                    **({"openreview_url": openreview_links[0]} if openreview_links else {}),
                ))
            if len(records) != len(listed):
                raise ValueError(f"ICLR index/bulk coverage mismatch: {year}, {len(records)} vs {len(listed)}")
            self.log(event="duplicate_event_types_excluded", venue="ICLR", year=year, counts=dict(excluded))
        self.log(event="listing_parsed", venue="ICLR", year=year, source_url=listing, records=len(records))
        return records


def seed_legacy(records, legacy_path):
    old = [json.loads(line) for line in legacy_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    old = [r for r in old if r.get("venue") in TARGETS]
    by_url = {canonical_identity(r["url"]): r for r in records}
    by_title = {(r["venue"], r["year"], title_key(r["title"])): r for r in records}
    seeded = []
    for prior in old:
        current = by_url.get(canonical_identity(prior["url"]))
        if current is None:
            current = by_title.get((prior["venue"], prior["year"], title_key(prior["title"])))
        if current is None:
            raise ValueError(f"Legacy ML record absent from current official listings: {prior['id']}")
        current["id"] = prior["id"]
        current["url"] = prior["url"]
        current["legacy_seed"] = True
        current["legacy_source_file"] = legacy_path.as_posix()
        current["prior_collection_level"] = prior.get("collection_level", "unknown")
        current["prior_semantic_review_performed"] = prior.get("semantic_review_performed", False)
        # Explicit inspection fields, if present, remain historical and cannot
        # be mistaken for a new review performed by this metadata collector.
        historical_flags = {k: v for k, v in prior.items() if k.startswith("inspection_") or k.startswith("semantic_review_")}
        if historical_flags:
            current["prior_inspection_flags"] = historical_flags
        seeded.append(prior["id"])
    if len(seeded) != 150 or len(set(seeded)) != 150:
        raise ValueError(f"Expected all 150 unique historical ML records, got {len(seeded)}")
    return seeded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--legacy", type=Path, default=Path("output/research/historical-2022/papers.jsonl"))
    parser.add_argument("--refresh", action="store_true", help="Refetch bulk source responses instead of using verified local cache")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    collector = Collector(args.out_dir, args.refresh)
    started = time.monotonic()
    groups = [(venue, year) for venue in TARGETS for year in YEARS]
    records = []
    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            jobs = [pool.submit(getattr(collector, venue.lower()), year) for venue, year in groups]
            for job in jobs:
                records.extend(job.result())
        seeded = seed_legacy(records, args.legacy)
        records.sort(key=lambda r: (r["venue"], r["year"], r["id"]))
        assert len({r["id"] for r in records}) == len(records)
        assert len({canonical_identity(r["url"]) for r in records}) == len(records)
        assert all(r["title"] and r["authors"] and 2020 <= r["year"] <= 2022 for r in records)
        assert all(r["collection_level"] == "citation_metadata" and r["semantic_review_performed"] is False for r in records)
        assert all("abstract" not in r and not any("local_path" in k for k in r) for r in records)
        counts = Counter(r["venue"] for r in records)
        assert all(counts[venue] >= int(target * 1.1) for venue, target in TARGETS.items())
        (args.out_dir / "ml-candidates.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
        responses = [event for event in collector.events if event["event"] in ("network_response", "cache_hit")]
        summary = {
            "records": len(records), "venue_counts": dict(counts),
            "venue_year_counts": {f"{venue}-{year}": sum(r["venue"] == venue and r["year"] == year for r in records) for venue, year in groups},
            "year_counts": dict(Counter(r["year"] for r in records)),
            "legacy_seed_records": len(seeded), "legacy_seed_ids": seeded,
            "requested_venue_targets": TARGETS,
            "candidate_reserves_over_target": {v: counts[v] - n for v, n in TARGETS.items()},
            "network_requests": sum(e["event"] == "network_response" for e in collector.events),
            "cache_hits": sum(e["event"] == "cache_hit" for e in collector.events),
            "source_responses": responses,
            "max_concurrency_per_host": 2, "accessed_date": ACCESSED,
            "collection_level": "citation_metadata", "semantic_reviewed_papers_this_collection": 0,
            "scope": "ICML, ICLR, NeurIPS 2020--2022 main-conference papers only; NeurIPS 2022 Datasets and Benchmarks excluded; ICLR duplicate Oral events excluded",
            "raw_cache_policy": "Raw official bulk responses retained locally for reproducibility; not intended for publication",
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
        (args.out_dir / "ml-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in summary.items() if k not in ("source_responses", "legacy_seed_ids")}, ensure_ascii=False, indent=2))
    finally:
        # Keep the original fetch receipts when a later run only reads cache.
        with (args.out_dir / "ml-requests.jsonl").open("a", encoding="utf-8") as handle:
            handle.write("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in collector.events))


if __name__ == "__main__":
    main()
