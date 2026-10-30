#!/usr/bin/env python3
"""Collect pre-2023 CVPR/ICCV citation metadata from official bulk proceedings.

Requires requests and beautifulsoup4. Run from the repository root:
  python output/paper-writing/scripts/collect_library_cv.py

Only proceedings listing pages are requested. No paper pages, PDFs, abstracts,
or full text are fetched. Local raw-page caches are not publication artifacts.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import re
import threading
import time
import unicodedata
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

BASE = 'https://openaccess.thecvf.com/'
PLAN = [('CVPR', 2020), ('CVPR', 2021), ('CVPR', 2022),
        ('ICCV', 2019), ('ICCV', 2021)]


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def canonical_url(url):
    parts = urlsplit(url)
    return urlunsplit(('https', parts.netloc.lower().removeprefix('www.'),
                       parts.path, '', ''))


def normalized_title(title):
    return ''.join(c for c in unicodedata.normalize('NFKC', title).casefold()
                   if c.isalnum())


class Fetcher:
    """At most two workers, globally spaced request starts, transparent retries."""

    def __init__(self, cache_dir, refresh=False):
        self.cache_dir = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.refresh = refresh
        self.local = threading.local()
        self.lock = threading.Lock()
        self.last_start = 0.0
        self.log = []

    def add_log(self, **row):
        with self.lock:
            self.log.append({'logged_at_utc': utc_now(), **row})

    def session(self):
        if not hasattr(self.local, 'session'):
            self.local.session = requests.Session()
            self.local.session.headers['User-Agent'] = (
                'ResearchCitationLibrary/1.0 (public proceedings metadata; '
                'two workers maximum; no full-text crawling)')
        return self.local.session

    def get(self, url):
        cache = self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + '.json')
        if cache.exists() and not self.refresh:
            payload = json.loads(cache.read_text(encoding='utf-8'))
            self.add_log(url=url, status='cache_hit',
                         original_accessed_at_utc=payload['accessed_at_utc'],
                         response_sha256=payload['response_sha256'])
            return payload
        for attempt in range(1, 4):
            # This lock limits request-start frequency across both worker threads.
            with self.lock:
                delay = max(0.0, 0.4 - (time.monotonic() - self.last_start))
                if delay:
                    time.sleep(delay)
                self.last_start = time.monotonic()
            try:
                response = self.session().get(url, timeout=(10, 60))
            except requests.RequestException as exc:
                self.add_log(url=url, status='network_error', attempt=attempt,
                             error=str(exc))
                if attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise
            stamp = utc_now()
            digest = hashlib.sha256(response.content).hexdigest()
            self.add_log(url=url, final_url=response.url, status='http_response',
                         http_status=response.status_code, attempt=attempt,
                         bytes=len(response.content), response_sha256=digest)
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt == 3:
                    response.raise_for_status()
                retry_after = response.headers.get('Retry-After', '')
                try:
                    pause = max(0.0, float(retry_after))
                except ValueError:
                    try:
                        pause = max(0.0, (parsedate_to_datetime(retry_after) -
                                          datetime.now(timezone.utc)).total_seconds())
                    except (TypeError, ValueError, OverflowError):
                        pause = float(2 ** attempt)
                self.add_log(url=url, status='retry_wait', attempt=attempt,
                             retry_after_seconds=pause)
                time.sleep(pause)
                continue
            # No retry, alternate-host substitution, or challenge bypass for 403.
            response.raise_for_status()
            payload = {'url': url, 'final_url': response.url,
                       'accessed_at_utc': stamp, 'http_status': response.status_code,
                       'response_sha256': digest, 'html': response.text}
            cache.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
            return payload
        raise RuntimeError(f'Unable to fetch {url}')


def parse_page(payload, venue, year):
    soup = BeautifulSoup(payload['html'], 'html.parser')
    found, rejected = [], []
    pattern = re.compile(rf'^/content(?:_|/){venue}_?{year}/html/[^/]+\.html$')
    for ordinal, node in enumerate(soup.select('dt.ptitle'), 1):
        anchor = node.select_one('a[href]')
        if not anchor:
            rejected.append({'ordinal': ordinal, 'reason': 'missing_title_link'})
            continue
        url = canonical_url(urljoin(BASE, anchor['href']))
        parts = urlsplit(url)
        if (parts.netloc != 'openaccess.thecvf.com' or
                not pattern.fullmatch(parts.path) or 'workshop' in url.lower()):
            rejected.append({'ordinal': ordinal, 'url': url,
                             'reason': 'not_exact_main_proceedings_html_path'})
            continue
        title = anchor.get_text(' ', strip=True)
        author_block = node.find_next_sibling('dd')
        authors = []
        if author_block:
            authors = [tag.get('value', '').strip() for tag in
                       author_block.select('input[name="query_author"]')]
            if not authors:
                authors = [tag.get_text(' ', strip=True).rstrip(',').strip()
                           for tag in author_block.select('form.authsearch a')]
        authors = [name for name in authors if name]
        if not title or not authors:
            rejected.append({'ordinal': ordinal, 'url': url,
                             'reason': 'missing_title_or_author_list'})
            continue
        ident = f'cv-{venue.lower()}-{year}-' + hashlib.sha256(url.encode()).hexdigest()[:12]
        found.append({'id': ident, 'title': title, 'authors': authors,
                      'venue': venue, 'year': year, 'url': url,
                      'source_listing_url': payload['url'],
                      'source_system': 'CVF Open Access official main-conference proceedings',
                      'accessed_date': payload['accessed_at_utc'][:10],
                      'accessed_at_utc': payload['accessed_at_utc'],
                      'source_listing_sha256': payload['response_sha256'],
                      'source_listing_ordinal_one_based': ordinal,
                      'collection_level': 'citation_metadata',
                      'semantic_review_performed': False,
                      'selection_method': 'All valid citation entries from official main-conference bulk listings; candidate pool for deterministic stratified selection.'})
    return soup, found, rejected


def collect_stratum(fetcher, venue, year):
    start_url = f'{BASE}{venue}{year}' + ('?day=all' if year >= 2021 else '')
    payload = fetcher.get(start_url)
    soup, records, rejected = parse_page(payload, venue, year)
    pages = [payload['url']]
    if not records:
        day_urls = sorted({urljoin(BASE, anchor['href']) for anchor in soup.select('a[href]')
                           if re.fullmatch(rf'{venue}{year}\.py\?day=\d{{4}}-\d{{2}}-\d{{2}}',
                                           anchor['href'])})
        if not day_urls:
            raise RuntimeError(f'No main-conference citation entries or day links: {start_url}')
        for url in day_urls:
            day_payload = fetcher.get(url)
            _, day_records, day_rejected = parse_page(day_payload, venue, year)
            records.extend(day_records)
            rejected.extend(day_rejected)
            pages.append(url)
    if not records:
        raise RuntimeError(f'No valid records for {venue} {year}')
    unique = {}
    for record in records:
        unique.setdefault(record['url'], record)
    fetcher.add_log(url=start_url, status='parsed_stratum', venue=venue, year=year,
                    listing_pages=pages, raw_valid_entries=len(records),
                    unique_records=len(unique), rejected_entries=len(rejected))
    return list(unique.values()), {'venue': venue, 'year': year,
                                  'listing_pages': pages,
                                  'valid_entries_before_url_deduplication': len(records),
                                  'unique_records': len(unique),
                                  'rejected_entries': rejected}


def preserve_seeds(records, seed_file):
    seeds = [json.loads(line) for line in seed_file.read_text(encoding='utf-8').splitlines()
             if line.strip()]
    seeds = [row for row in seeds if (row.get('venue'), row.get('year')) in PLAN]
    by_url = {canonical_url(row['url']): row for row in records}
    by_title = {(row['venue'], row['year'], normalized_title(row['title'])): row
                for row in records}
    missing = []
    for seed in seeds:
        current = by_url.get(canonical_url(seed['url'])) or by_title.get(
            (seed['venue'], seed['year'], normalized_title(seed['title'])))
        if current is None:
            missing.append(seed['id'])
            continue
        current['id'] = seed['id']
        current['historical_seed'] = True
        current['historical_provenance'] = {
            'source_metadata_file': seed_file.as_posix(),
            'accessed_date': seed.get('accessed_date'),
            'collection_level': seed.get('collection_level'),
            'semantic_review_performed': bool(seed.get('semantic_review_performed', False)),
            'semantic_review_sections': seed.get('semantic_review_sections', []),
            'full_paper_read': bool(seed.get('full_paper_read', False)),
            'note': 'Prior collection evidence is preserved separately. This new collection fetched citation listings only; no new semantic review was performed.'}
    if missing:
        raise RuntimeError(f'Historical CVF seed records missing from official bulk listings: {missing}')
    return len(seeds), sum(bool(seed.get('semantic_review_performed')) for seed in seeds)


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path,
                        default=Path('output/research/library-10000/shards'))
    parser.add_argument('--seed-file', type=Path,
                        default=Path('output/research/historical-2022/papers.jsonl'))
    parser.add_argument('--refresh', action='store_true',
                        help='Refetch cached listing pages, keeping request limits and retry policy.')
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    fetcher = Fetcher(args.out_dir / '.cv-cache', args.refresh)
    records, strata, failures = [], [], []
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = {pool.submit(collect_stratum, fetcher, venue, year): (venue, year)
                 for venue, year in PLAN}
        for future in as_completed(tasks):
            venue, year = tasks[future]
            try:
                rows, stratum = future.result()
                records.extend(rows)
                strata.append(stratum)
                print(f'{venue} {year}: {len(rows)} citation records', flush=True)
            except Exception as exc:
                failures.append({'venue': venue, 'year': year, 'error': str(exc)})
                fetcher.add_log(status='stratum_failure', venue=venue, year=year,
                                error=str(exc))
    log_path = args.out_dir / 'cv-request-log.jsonl'
    log_path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n'
                                for row in fetcher.log), encoding='utf-8')
    if failures:
        write_json(args.out_dir / 'cv-failures.json', failures)
        raise SystemExit(f'Collection failed for {len(failures)} strata; see cv-failures.json')
    seed_count, historical_reviews = preserve_seeds(records, args.seed_file)
    records.sort(key=lambda row: (row['venue'], row['year'], row['title'].casefold(), row['url']))
    assert len(records) == len({row['url'] for row in records})
    assert len(records) == len({row['id'] for row in records})
    assert all(row['authors'] and row['title'] and row['year'] <= 2022 for row in records)
    target = args.out_dir / 'cv-candidates.jsonl'
    target.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n'
                              for row in records), encoding='utf-8')
    counts = Counter(row['venue'] for row in records)
    assert counts['CVPR'] >= 2750 and counts['ICCV'] >= 1100
    summary = {
        'generated_at_utc': utc_now(), 'cutoff_year_inclusive': 2022,
        'record_count': len(records), 'venue_counts': dict(sorted(counts.items())),
        'publication_strata': sorted(strata, key=lambda row: (row['venue'], row['year'])),
        'historical_seeds_preserved': seed_count,
        'historical_records_with_prior_semantic_review': historical_reviews,
        'new_semantic_reviews': 0, 'new_paper_page_requests': 0,
        'new_full_text_requests': 0,
        'network_requests': sum(row['status'] in ('http_response', 'network_error')
                                for row in fetcher.log),
        'successful_http_responses': sum(row.get('http_status') == 200 for row in fetcher.log),
        'http_response_bytes': sum(row.get('bytes', 0) for row in fetcher.log),
        'cache_hits': sum(row['status'] == 'cache_hit' for row in fetcher.log),
        'failures': failures,
        'network_policy': 'At most two concurrent listing requests for the one host; request starts at least 0.4 seconds apart; three attempts maximum for network/5xx/429 errors; honors Retry-After; no 403 retry or challenge bypass.',
        'scope': 'Complete available citation candidate pool for CVPR 2020/2021/2022 and ICCV 2019/2021 official main proceedings. Workshops excluded using exact venue/year content paths. No abstract/full-text extraction or new semantic reading.',
        'selection': 'Candidates sorted by venue, year, title.casefold(), URL. Final library quota selection occurs downstream.',
        'cache': 'Local .cv-cache contains raw official listing responses with UTC access time and SHA256; it is not a public library artifact.',
        'output': target.as_posix()}
    write_json(args.out_dir / 'cv-summary.json', summary)
    write_json(args.out_dir / 'cv-failures.json', failures)
    print(json.dumps({key: summary[key] for key in ('record_count', 'venue_counts',
                     'historical_seeds_preserved', 'network_requests', 'cache_hits', 'failures')}), flush=True)


if __name__ == '__main__':
    main()
