# Paper Review Lab

An evidence-backed manuscript review workbench and portable writing toolkit. Make the reasoning inspectable, record what remains unknown, and revise the weakest part of the argument.

[Open the live workbench](https://optimizer077.github.io/paper-review-lab/) · [Download the toolkit](https://optimizer077.github.io/paper-review-lab/downloads/paper-review-lab.zip) · [Toolkit guide](toolkit/README.md) · [Writing skill](toolkit/paper-writing/SKILL.md)

## What is included

- **24 anchored criteria across five domains**, adapted to four contribution profiles: empirical ML, theory, clinical research, and systematic reviews.
- **Transparent scoring** with evidence, rationale, coverage, confidence, domain results, and critical blockers. Aggressive mode preserves the raw score and applies the lowest triggered score cap.
- **A local browser workbench** for manual assessment, JSON import/export, rubric exploration, and a searchable library of **300 citation metadata records from 2018–2022**.
- **A Python toolkit** for mechanical manuscript audits, versioned scorecards, and task packets for **ten independent reviewer roles**.

The website and core command-line tools have no AI backend. A person or capable agent must inspect the manuscript and its evidence. Generated packets are review tasks; they are not completed reviews. Browser entries remain in the tab, with no automatic saving—export your JSON before closing it.

## Quick start

Use Python 3.10+ from the repository root. The workbench requires HTTP so its local JSON files can load:

```sh
python -m http.server 8765 --directory docs
```

Open `http://localhost:8765`. No package installation or build step is required.

Audit the bundled fictional manuscript or prepare reviewer packets:

```sh
python toolkit/paper-writing/scripts/paper_harness.py audit toolkit/examples/manuscript.md --context toolkit/examples/project.json --out audit.json
python toolkit/paper-writing/scripts/paper_harness.py plan toolkit/examples/manuscript.md --context toolkit/examples/project.json --out review-plan.json
```

Export an assessment from the workbench, then score it locally:

```sh
python toolkit/paper-writing/scripts/score_evaluation.py assessment.json --rubric toolkit/paper-writing/assets/manuscript-rubric.json --strictness aggressive --out scored.json --markdown review.md
```

See the [harness guide](toolkit/paper-writing/references/harness-guide.md) and [scorecard](toolkit/paper-writing/references/evaluation-scorecard.md) for inputs, commands, and interpretation.

## Verification

The portable toolkit has 98 unit tests. The browser parity check covers 176 fictional scenarios across the four bundled integer-weight profiles and requires Node.js 20+ alongside Python 3.10+.

```sh
python -m unittest discover -s toolkit/validation -p 'test_*.py' -q
python tests/check_site_parity.py
```

Parity covers scores, domain results, coverage, readiness, caps, and rubric/policy fingerprints. Custom floating-point rubric serialization is outside this compatibility claim.

## Evidence and scope

The historical library hosts citation metadata and original editorial notes; it does not distribute abstracts or article bodies. Collection, selected-section inspection, and full scientific review are distinct. These selected venues and papers are neither an objective venue ranking nor a representative sample. Bundled manuscript fixtures and demonstration assessments contain fictional data; the citation registry identifies actual historical papers.

Scoring thresholds are editorial conventions without prospective real-manuscript calibration. A score, audit pass, or completed assessment does not certify scientific validity, establish submission readiness, or predict acceptance.

GitHub Pages serves the buildless site from `main:/docs`. See [site maintenance and provenance](docs/README.md) for deployment details.
