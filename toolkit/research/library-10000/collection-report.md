# Expanded historical resource library

Validated **10,000 unique citation records**, published during 2018–2022, from eleven explicitly selected main conferences and flagship journals.

| Venue | Records |
| --- | ---: |
| BMJ | 200 |
| CVPR | 2,500 |
| ICCV | 1,000 |
| ICLR | 1,500 |
| ICML | 2,000 |
| JAMA | 200 |
| NEJM | 200 |
| Nature | 100 |
| Nature Medicine | 100 |
| NeurIPS | 2,000 |
| The Lancet | 200 |

All 300 original citation IDs are retained. Additional selection balances publication-year counts within each venue, then uses ascending SHA-256 of canonical source URLs. Fixed quotas and accessible strata form a convenience resource index, not a representative literature review or an objective venue ranking.

## Sources and eligibility

Conference metadata comes from official CVF main proceedings, NeurIPS main-conference proceedings, PMLR ICML volumes119/139/162, and ICLR accepted-poster datasets linked by the official virtual programs. Workshops, duplicate oral/poster events, and the separate NeurIPS datasets/benchmarks track are excluded.

Journal metadata comes from Europe PMC core records with exact flagship ISSNs, publication year and first-publication date by 2022. Eligibility filters exclude letters, editorials, corrections, retractions, protocols, preprints and narrative reviews. Original research and systematic reviews/meta-analyses are eligible. Nature is restricted to health-related query terms.

Source URLs, listing/API provenance, authors, dates and citation identifiers are recorded. Raw proceedings caches and API responses remain local; the public library contains no article abstracts, extracted text, PDFs or XML bodies.

## What this does and does not establish

This expansion adds citation metadata, not new selected-section inspections or scientific reviews. The original writing notes retain their disclosed basis: a 300-paper collection, 238 locally downloaded bodies and 18 abstract/selected-section inspections. None of these counts is a scientific-quality or acceptance estimate.

The independent audit checks record eligibility, identifiers, provenance, metadata consistency and reproducibility; it does not certify the science in the papers.

## Reproduce

```sh
python paper-writing/scripts/collect_library.py --output-root research/library-10000 --seed research/historical-2022/papers.jsonl --collect
python paper-writing/scripts/collect_library.py --output-root research/library-10000 --seed research/historical-2022/papers.jsonl --validate
```

The first command uses requests and beautifulsoup4, three bounded bulk collectors, source caches and explicit selection. The validator/merge uses Python standard library. Individual collectors have --refresh options for a fresh source fetch. A source change may change candidates; source-response receipts and the final corpus hash make that difference inspectable.

Registry SHA-256: `0c2780e1dec887cd403dab8a7148c1e08486eb6c6ad37dfc3ef65fceca52dae7`.
