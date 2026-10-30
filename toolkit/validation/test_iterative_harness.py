"""Offline behavior checks for focused, revision-bound multi-reviewer plans."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


OUTPUT = Path(__file__).resolve().parents[1]
SCRIPT = OUTPUT / "paper-writing" / "scripts" / "paper_harness.py"
spec = importlib.util.spec_from_file_location("iterative_harness", SCRIPT)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


class IterativeHarnessTests(unittest.TestCase):
    def setUp(self):
        self.context = h.load_json(OUTPUT / "examples" / "project.json")
        self.text = h.read_manuscript(OUTPUT / "examples" / "manuscript.md")

    def plan(self, selected="argument,evidence,readability", text=None, context=None):
        return h.build_plan(text or self.text, context or self.context, h.load_roles(selected=selected))

    def report(self, plan, rid):
        return {
            "version": 1, "role_id": rid,
            "manuscript_sha256": plan["manuscript_sha256"],
            "context_sha256": plan["context_sha256"],
            "verdict": "pass", "findings": [],
            "checks": [{
                "id": "synthetic-review", "check_type": "semantic", "status": "passed",
                "reviewed_by": "agent", "reviewer": "synthetic-software-fixture",
                "evidence": ["Invented software fixture judgment, not a scientific review."],
                "rationale": "Exercises revision and selected-role merge behavior only.",
            }],
        }

    def merge(self, plan, reports):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for index, report in enumerate(reports):
                target = Path(tmp) / f"review-{index}.json"
                h.emit(report, target)
                paths.append(target)
            return h.merge_reviews(plan, paths)

    def test_focused_cli_exports_only_selected_packets_with_blind_reader_isolation(self):
        context = copy.deepcopy(self.context)
        context["thesis"] = "AUTHOR-ANSWER-KEY-SENTINEL"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context_file = root / "context.json"
            h.emit(context, context_file)
            target = root / "round-1.json"
            code = h.main([
                "plan", str(OUTPUT / "examples" / "manuscript.md"),
                "--context", str(context_file), "--select-roles", "evidence,readability,argument",
                "--out", str(target),
            ])
            self.assertEqual(code, 0)
            plan = h.load_json(target)
            self.assertEqual(plan["expected_role_ids"], ["evidence", "readability", "argument"])
            self.assertEqual(plan["execution"], "packets_only_no_agents_dispatched")
            packets = {task["role_id"]: h.load_json(task["packet_file"]) for task in plan["tasks"]}
            self.assertEqual(set(packets), {"evidence", "readability", "argument"})
            self.assertNotIn("AUTHOR-ANSWER-KEY-SENTINEL", json.dumps(packets["readability"]))
            self.assertEqual(packets["evidence"]["context"]["thesis"], context["thesis"])
            comparison = h.load_json(packets["readability"]["comparison_context_file"])
            self.assertEqual(comparison["context"]["thesis"], context["thesis"])
            self.assertEqual(len(list((root / "round-1.packets").glob("*.json"))), 4)

    def test_default_ten_role_plan_remains_compatible(self):
        roles = h.load_roles()
        self.assertEqual(len(roles), 10)
        plan = h.build_plan(self.text, self.context, roles)
        result = self.merge(plan, [self.report(plan, role["id"]) for role in roles])
        self.assertEqual((result["status"], result["verdict"]), ("complete", "pass"))

    def test_custom_nonempty_role_set_can_be_filtered(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "roles.json"
            roles = [
                {"id": "theory", "instructions": "Inspect the actual assumptions and proof."},
                {"id": "notation", "instructions": ["Trace symbol definitions.", "Record exact locations."]},
            ]
            h.emit({"roles": roles}, target)
            self.assertEqual(len(h.load_roles(target)), 2)
            selected = h.load_roles(target, "notation")
            plan = h.build_plan(self.text, self.context, selected)
            self.assertEqual(plan["expected_role_ids"], ["notation"])
            self.assertEqual(self.merge(plan, [self.report(plan, "notation")])["verdict"], "pass")

    def test_empty_duplicate_unknown_and_malformed_selection_refused_without_writes(self):
        for selected in ("", "argument,", "argument,argument", "argument,no-such-role", "../argument"):
            with self.subTest(selected=selected), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / "round.json"
                with contextlib.redirect_stderr(io.StringIO()):
                    code = h.main([
                        "plan", str(OUTPUT / "examples" / "manuscript.md"),
                        "--context", str(OUTPUT / "examples" / "project.json"),
                        "--select-roles", selected, "--out", str(target),
                    ])
                self.assertEqual(code, 2)
                self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_custom_empty_or_filename_colliding_roles_refused(self):
        invalid_sets = [
            [],
            [{"id": "Reader", "instructions": "Read."}, {"id": "reader", "instructions": "Read."}],
            [{"id": "comparison-context", "instructions": "Read."}],
            [{"id": "reader.", "instructions": "Read."}],
            [{"id": "NUL", "instructions": "Read."}],
        ]
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "roles.json"
            for roles in invalid_sets:
                with self.subTest(roles=roles):
                    h.emit(roles, target)
                    with self.assertRaises(h.InputError):
                        h.load_roles(target)

    def test_focused_merge_requires_exactly_its_selected_roles(self):
        plan = self.plan("argument,evidence")
        reports = [self.report(plan, role) for role in plan["expected_role_ids"]]
        complete = self.merge(plan, reports)
        self.assertEqual((complete["status"], complete["verdict"]), ("complete", "pass"))
        self.assertEqual(complete["expected_role_ids"], ["argument", "evidence"])
        self.assertEqual(complete["check_summary"]["semantic"], 2)
        incomplete = self.merge(plan, reports[:1])
        self.assertEqual(incomplete["missing_roles"], ["evidence"])
        self.assertEqual((incomplete["status"], incomplete["verdict"]), ("incomplete", "blocked"))

    def test_extra_or_duplicate_review_cannot_make_focused_merge_pass(self):
        plan = self.plan("argument")
        report = self.report(plan, "argument")
        for extra in (copy.deepcopy(report), self.report(plan, "evidence")):
            with self.subTest(extra_role=extra["role_id"]):
                result = self.merge(plan, [report, extra])
                self.assertEqual(result["verdict"], "blocked")
                self.assertEqual(len(result["invalid_reviews"]), 1)

    def test_later_round_rejects_old_manuscript_or_context_review(self):
        first = self.plan("evidence")
        first_report = self.report(first, "evidence")
        changed_context = copy.deepcopy(self.context)
        changed_context["revision"] = "next-context"
        later_plans = [
            self.plan("evidence", text=self.text + "\nA new scope qualification.\n"),
            self.plan("evidence", context=changed_context),
        ]
        for later in later_plans:
            with self.subTest(hash_pair=(later["manuscript_sha256"], later["context_sha256"])):
                stale = self.merge(later, [first_report])
                self.assertEqual(stale["verdict"], "blocked")
                self.assertEqual(stale["missing_roles"], ["evidence"])
                self.assertIn("stale", stale["invalid_reviews"][0]["error"])
                fresh = self.merge(later, [self.report(later, "evidence")])
                self.assertEqual((fresh["status"], fresh["verdict"]), ("complete", "pass"))

    def test_template_is_incomplete_even_in_a_single_role_round(self):
        plan = self.plan("argument")
        result = self.merge(plan, [plan["tasks"][0]["report_template"]])
        self.assertEqual((result["status"], result["verdict"]), ("incomplete", "revise"))
        self.assertEqual(len(result["pending_semantic_checks"]), 1)

    def test_pruning_expected_roles_without_matching_tasks_is_invalid(self):
        plan = self.plan("argument,evidence")
        plan["expected_role_ids"] = ["argument"]
        with self.assertRaisesRegex(h.InputError, "match expected_role_ids"):
            self.merge(plan, [self.report(plan, "argument")])

    def test_duplicate_or_nonobject_manifest_tasks_are_invalid(self):
        for task_change in (lambda p: p["tasks"].append(p["tasks"][0]), lambda p: p.update(tasks=["argument"])):
            plan = self.plan("argument")
            task_change(plan)
            with self.assertRaises(h.InputError):
                self.merge(plan, [self.report(plan, "argument")])

    def test_legacy_plan_without_tasks_remains_compatible(self):
        plan = self.plan()
        del plan["tasks"]
        result = self.merge(plan, [self.report(plan, rid) for rid in plan["expected_role_ids"]])
        self.assertEqual((result["status"], result["verdict"]), ("complete", "pass"))


if __name__ == "__main__":
    unittest.main()
