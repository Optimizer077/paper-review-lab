# Independent citation-library audit

Reviewed offline on 2026-10-30. **PASS for the checked metadata, selection and source-provenance requirements after the repairs below.** This is a citation-metadata audit, not abstract reading, full-paper reading or scientific assessment.

The final [registry](papers.jsonl) contains exactly **10,000 unique records**, retains all **300 initial IDs** with matching normalized titles, venues and years, and matches the [summary](summary.json). Registry SHA-256:

```text
0c2780e1dec887cd403dab8a7148c1e08486eb6c6ad37dfc3ef65fceca52dae7
```

| Venue | Final records |
| --- | ---: |
| CVPR | 2,500 |
| ICCV | 1,000 |
| NeurIPS | 2,000 |
| ICML | 2,000 |
| ICLR | 1,500 |
| NEJM | 200 |
| The Lancet | 200 |
| JAMA | 200 |
| BMJ | 200 |
| Nature Medicine | 100 |
| Nature | 100 |

All publication years are at or before 2022. Within each venue's available collection years, selected year counts differ by at most one. The candidate pools contain 7,887 CV, 13,045 ML and 1,200 medical records. These are explicit convenience quotas with deterministic selection, not a ranking or representative sample.

## Verification

The independent [regressions](../../validation/test_library.py) use the shipped APIs and real artifacts, with synthetic boundary cases rather than copying implementation constants. Reproduce from the toolkit root (the directory containing `paper-writing/` and `validation/`):

```powershell
python -m unittest discover -s validation -p test_library.py -v
```

Final local result: **13 tests passed**. Tests cover cutoff and Boolean-year rejection, nonempty authors, exact medical ISSN and first-date constraints, official hosts and main-conference exclusions, ID/DOI/normalized-title/canonical-URL duplicates, metadata-only fields, exact quotas, deterministic balanced selection, retained seed identity, missing/duplicate seeds, insufficient pools, and worker command/seed forwarding. The pure medical-author parser is exercised with a mocked network-module import, so synthetic tests require only the standard library. Tests resolve the output root from their own location.

Offline source checks verified 11 cached ML response hashes and 12 cached CVF listing hashes. All 3,500 selected CVF links match exact main-conference/year paths. All 666 selected NeurIPS 2022 links have the Conference suffix. All 1,500 selected ICLR author arrays match official cached bulk sources; the 2021/2022 records also match the official accepted-poster index and titles. This independently checks the Poster filter, rather than treating every bulk event as a paper.

All 1,000 selected medical author arrays match refreshed sanitized source caches. All 32 medical cache files declare the corrected ordered-author occurrence policy; all 1,200 medical candidate author arrays match those caches. Specific closure probes preserve three `Wang J` entries for `med-32492084` and two each of `Zhang Y` and `Yang X` for `med-34037666`. All selected medical first-publication years agree with their recorded publication year and satisfy the cutoff; exact journal ISSNs and excluded publication types were checked.

Private raw caches are not a public-library dependency: the cache-specific test skips when they are absent. The final-registry test skips when the registry is still being assembled, and explicitly identifies a missing historical seed artifact in an export. No HTTP requests were made by this audit.

## Findings and verified closure

- The collection orchestrator initially passed an unsupported medical output argument and did not forward seed paths. The medical worker now accepts the shard-directory alias and every worker receives its supported seed flag. Mocked command checks and the medical CLI help confirm closure.
- The original merger validator accepted CVPR workshop shorthand paths and NeurIPS 2022 Dataset and Benchmarks paths on official hosts. Exact CVF paths, NeurIPS Conference suffix and ICML year/volume checks now reject those cases. This finding concerned fail-closed validation; it did not establish contamination of the correctly filtered candidate pools.
- The medical parser originally deduplicated author entries by rendered name, losing repeated initials/name strings. The parser now preserves source order and occurrences, all affected caches were refreshed, seed metadata was refreshed with IDs retained, and the library was merged again. The synthetic collision test and actual multiplicity/cache checks pass.
- Direct registry validation originally accepted `abstractText`, `body` and additional local-path fields even though conversion stripped them. The merger now uses an explicit allowed-field set; the leakage regressions pass. The actual final registry contains no article-text or host-path fields.

No unresolved defect was reproduced within this scope. Saved source responses and matching hashes establish local provenance consistency, not fresh publisher authentication or correctness of every upstream bibliographic claim. Nonempty author strings do not establish unique person identities. Metadata collection does not establish that these papers were read, judged exemplary or scientifically validated. The original 300-paper collection and its limited inspection history remain separate.

Only this audit and `validation/test_library.py` were authored by the independent audit agent; production repairs were made by the owning agents.
