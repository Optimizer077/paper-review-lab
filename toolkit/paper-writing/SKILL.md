---
name: paper-writing
description: Draft, revise, and iteratively review scientific manuscripts using evidence checks, consistent terminology, and coordinated independent reviewers. Use for paper sections, whole manuscripts, and reviewer responses in ML, computer vision, and health research.
---

# Paper writing

Produce the requested manuscript or edit, preserving the actual science. Use this skill for academic argument and prose; use the appropriate document or LaTeX tools when rendered layout is also requested. The bundled harness provides inspectable mechanical checks and reviewer packets, not an automatic scientific-quality verdict.

## Establish the working record

The resource library contains 10,000 citation records from 2022 or earlier, restricted to CVPR, ICCV, NeurIPS, ICLR, ICML, NEJM, The Lancet, JAMA, BMJ, Nature Medicine, and Nature. The original 300-paper collection and its 18 abstract or selected-section inspections remain the basis of the existing writing notes; the expanded metadata index does not establish that these additional papers were read. Use [historical paper lessons](references/historical-paper-lessons.md) for these examples. Exclude later papers and workshops from this reference collection; do not infer that every paper at a named venue is exemplary. This cutoff governs the example corpus, not the manuscript's own date or the author's future literature needs. Current submission instructions remain a separate compliance reference.

Infer the audience, contribution type, requested scope, manuscript stage, target venue/year/track, and available evidence. Work with existing drafts and records. Missing venue details do not prevent a useful section edit; label any provisional structure. Follow the author's format rather than imposing IMRAD on theory, position papers, or narrative reviews.

For a substantial draft or several writers, create a versioned project context using [the project template](assets/project-template.json). Record the question, thesis, terminology, protected facts, source passages with locators, claim status, and section dependencies. A source ID and a `supported` label are declarations to inspect, not proof. Separate proposed experiments from completed work. Keep essential limitations with their claims.

Do not invent results, methods, datasets, citations, ethics approvals, registrations, author declarations, or completed revisions. For a material missing fact, use an explicit unresolved marker in a working draft or explain the gap outside clean prose. Preserve comparators, denominators, metric direction, units, negation, uncertainty definitions, and generalization scope during editing.

## Choose the relevant work

- For iterative revision or coordinated multi-agent review, read [the iterative review workflow](references/iterative-review.md). Select useful complementary roles and a bounded round budget; a simple edit can finish directly. Use actual agent tools when available and authorized, and record the reviewers that actually ran.
- For an outline, title, abstract, introduction, related work, methods, results, or discussion, read [section craft](references/section-craft.md). Build paragraphs around the scientific argument and their supporting evidence. Do not force every paper into the same introduction formula.
- For jargon, acronyms, symbols, wording, or reader difficulty, read [clarity and consistency](references/clarity-and-consistency.md). For changed conceptual roles, units, denominators, or scientific meaning across sections, also use [concept consistency](references/concept-consistency.md). Retain precise technical language; distinguish permitted aliases from changes in meaning.
- For claim support, comparisons, uncertainty, reproducibility, or medical inference, read [evidence review](references/evidence-review.md). Select checks by study design and contribution type.
- For submission preparation, read [venue profiles](references/venue-profiles.md), then verify the exact current official instructions for the intended cycle, track, and stage. Historical policies are examples, not standing requirements.
- For a whole-paper or explicitly rigorous review, read [the review protocol](references/review-protocol.md). Use [the ten reviewer roles](assets/review-roles.json) when independent perspectives will help. A narrow edit usually needs only the relevant passes.
- When a score is requested, use [scoring v2](references/evaluation-scorecard.md), [aggressive review](references/aggressive-review.md), [category boundaries](references/evaluation-categories.md), and [the evaluation protocol](references/evaluation-protocol.md). New assessments use `aggressive` strictness unless the author requests standard mode. Select the appropriate contribution profile, use the 24 anchored criteria, require evidence and rationale, and report raw and effective scores, caps, coverage, confidence, domain scores and critical blockers separately. For a narrow task leave unrelated criteria unassessed; do not expand the task just to obtain a complete number. A reviewed scorecard is not submission approval.

- For writing manuals, courses, reporting guidance or tool support, read [the task-by-task support guide](references/writing-support-guide.md) and search [the annotated resource catalog](references/writing-resources.md). Choose a source for the actual writing task and contribution type. Preserve its access, version and inspection limits; a book listing is not a full reading, and tool documentation is not an accuracy benchmark.

## Draft and reconcile

Make the question and contribution understandable before polishing individual sentences. For each central claim, identify the supporting experiment, analysis, proof, or source passage and the condition that limits it. A lack of prior work alone does not establish importance; a novel method or state-of-the-art score is not required for every contribution.

During revision, preserve the author's scientific stance and confidence. Explain supported findings directly; separate observation, interpretation, and speculation. Inspect the source passage for consequential citations. Citation membership, paper titles, and neighboring sentences do not establish entailment.

After a substantive change, reconcile the title, abstract, introduction, contribution list, methods, results, captions, discussion, and conclusion that were supplied. Check the main finding, terminology, sample, uncertainty, and scope against the same context revision. If source material is partial, state which consistency checks remain unperformed.

For a reviewer response, connect each comment to a substantive answer and a verified revision location. Distinguish completed changes from proposed analyses. Explain justified disagreements without inventing extra experiments or page numbers.

## Iterate with independent reviewers

When iterative work is requested, carry out the loop: freeze the supplied draft and evidence, obtain independent observations, adjudicate findings against their sources, revise supported issues, then verify the changed artifact. For substantial or resumable work, use [the iteration state template](assets/iteration-state-template.json) and [revision ledger](assets/revision-ledger-template.json). A short section can keep the same essential provenance, findings, verification and stopping decision in one compact run note alongside its saved reviews. Keep these records outside clean manuscript prose.

Default to at most three review-and-revision rounds unless the author sets another limit. Stop sooner when no material supported revision remains, essential evidence is unavailable, or two consecutive rounds make no verified progress. A round limit or stalled review is not convergence. Preserve the strongest evidence-supported revision and return unresolved decisions; do not chase a score or keep rewriting equivalent prose.

Use one editor to reconcile and write the manuscript. Assign reviewers complementary questions, frozen inputs, exact output paths, and an explicit access scope; run in waves within the runtime's actual available capacity. Reviewers report findings rather than concurrently editing the same draft. Create a blind reader in a fresh context containing only the manuscript and reading instructions; save teach-back before supplying author intent, source records, or other reviews. A reviewer who already saw those materials cannot claim a blind pass.

After revision, regenerate affected packets with current manuscript/context hashes, re-review consequential changes, and reconcile dependent sections. Every report in a completed merged plan must match that round's inputs. Keep earlier reviews as history and preserve justified disagreement. For advanced review, add a targeted source, methods, statistical, proof, or adversarial perspective when it addresses an actual uncertainty; use the contribution profile rather than a generic checklist. Scoring remains conditional on a request for a score.

## Use the harness proportionately

Run `python scripts/paper_harness.py --help` from this skill directory. See [the harness guide](references/harness-guide.md) for concrete commands and limitations. The checker accepts text, Markdown, and common LaTeX structures; it does not render figures or fully parse TeX.

An audit can check registered IDs, literal facts, declared variants, unresolved markers, and configured section limits. Its warnings are prompts for inspection, not automatic edits. A passing audit does not establish that a citation exists, a result is correct, a number refers to the right cohort, or the paper is readable.

For multiple agents, generate a plan using the needed `--select-roles` or a custom `--roles` file, dispatch its independent roles using available agent tools, and merge exactly the selected roles. Omitting role selection retains the bundled ten-role plan. Record actual launches, completions, access failures, and report paths. The CLI generates task packets; it does not call an LLM service. Require evidence and locations in reviews, preserve manuscript/context hashes, and invalidate stale reviews after revisions. Generated packets are pending work until reviewers actually return results. If delegation is unavailable, perform scoped sequential passes and disclose the lack of independent agents.

Use blind reader teach-back to test understanding before showing the reader the intended thesis. Use a separate evidence reviewer to check whether that understanding is supported. Resolve supported blockers before optional prose polish; do not seek a fault quota or infer correctness from majority agreement.

## Deliver

Return the requested paper, section, revision, or review. For substantial review, include the principal changes, unresolved evidence issues, applicable verification limits, and next decision. For iterative work, also report completed rounds, actual reviewers, the retained revision, and the stopping reason. Keep review instructions out of manuscript prose. Do not call a manuscript submission-ready when material evidence or required declarations remain unresolved.

The source-backed research behind this skill is summarized in [the research basis](references/research-basis.md). The local convenience corpus illustrates writing choices; it does not measure what causes acceptance or establish universal stylistic rules.
