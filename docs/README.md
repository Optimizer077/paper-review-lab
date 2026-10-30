# Paper Review & Writing Assistant Lab

A buildless GitHub Pages site for writing and reviewing manuscripts with
evidence first: an evidence-backed review workbench with 24 anchored criteria,
four contribution profiles and aggressive scoring; a writing assistant page for
the paper-writing agent skill and offline harness; a writing-support hub; and a
searchable collection of 10,000 historical citation records from 2018–2022.

[Live site](https://optimizer077.github.io/paper-review-lab/) ·
[Writing assistant](https://optimizer077.github.io/paper-review-lab/writing.html) ·
[Repository quick start](../README.md) ·
[Toolkit download](downloads/paper-review-lab.zip)

Serve this folder over HTTP; opening `index.html` as a local file prevents JSON
fetches in many browsers:

```sh
python -m http.server 8765 --directory docs
```

Open `http://localhost:8765`. All CSS, JavaScript and data files are served from
this folder. The only external resources are Google Fonts: the stylesheet that
`site.css` imports from fonts.googleapis.com and the DM Sans and IBM Plex Mono
font files it loads from fonts.gstatic.com. Without them the pages fall back to
Arial or the system sans-serif, and Consolas or the system monospace.
Assessment entries and imported JSON remain in the tab; export before closing
it. The website does not read manuscripts or call an AI service.

## Verification

From the repository root, Python 3.10+ runs the portable toolkit tests (122 pass; one private-cache check is skipped):

```sh
python -m unittest discover -s toolkit/validation -p 'test_*.py' -q
python tests/check_site_parity.py
```

The parity check also needs Node.js 20+ and compares 176 fictional scenarios
against the bundled four integer-weight profiles. It covers raw/effective scores,
domain results, coverage, readiness, caps and policy/rubric fingerprints. Custom
floating-point rubric serialization is outside this browser compatibility claim.
Domain thresholds use unrounded ratios; displayed scores use two-decimal rounding.

## Publication and provenance

GitHub Pages serves `main:/docs` with `.nojekyll`; no package build or external
scripts are needed. Keep `data/manuscript-rubric.json` and
`data/scoring-policies.json` identical to their toolkit assets.

`data/corpus.json` includes citation metadata only. The original local collection
contained 300 abstracts and 238 downloaded bodies; neither is hosted here.
Collection is distinct from reading or scientific validation. Eighteen selected
papers were inspected at abstract or selected-section level; no claim of 10,000
complete scientific reviews is made. These are explicitly selected venues, not
an objective venue ranking or a representative paper sample.

`data/demo-assessment.json` contains fictional ratings and evidence to illustrate
arithmetic. It is not a real-paper assessment. Aggressive thresholds are original
editorial conventions with no prospective real-manuscript calibration; scores
are not acceptance predictions or scientific certification.

## Writing assistant page

`writing.html` is static guidance for the paper-writing agent skill
(`toolkit/paper-writing/SKILL.md`) and the offline harness. It explains the
five-step workflow (claim ledger, section drafting, mechanical audit, reviewer
packets with a blind reader first, optional scoring and revision), how to
install the skill for Claude Code or Codex, and six copy-paste prompts. It uses
`site.css`, `resources.css` and `writing.css`. A small `writing.js` only adds
local clipboard copy buttons; without JavaScript the commands and prompts remain
selectable text. The page has no backend. It does not read, write or review
manuscripts, and nothing on it calls an AI service. The skill runs inside an
agent the reader operates. Keep its commands in step with
`toolkit/paper-writing/references/harness-guide.md`, and re-check the Claude Code
(`~/.claude/skills/`) and Codex (`~/.agents/skills/`) skill locations when their
documentation changes.

## Writing support hub

`resources.html` uses the shared design and `resources.js`/`resources.css` to search 42 selected primary-source guides, manuals, courses, reporting standards and tool documentation. The live catalog is `data/writing-resources.json`; keep it equal to `toolkit/paper-writing/references/writing-resources.json`.

Before updating an entry, inspect the original provider and record its verification URL, date, access and inspection level. Books are metadata-only entries; limited indexed retrieval is disclosed. This catalog is separate from the historical paper cutoff.

```sh
python toolkit/paper-writing/scripts/validate_writing_resources.py toolkit/paper-writing/references/writing-resources.json
```
