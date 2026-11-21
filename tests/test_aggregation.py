"""Tests for aggregation semantics: denominators, token means, pairing, banners."""

from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.aggregation import (  # noqa: E402
    SYNTHETIC_BANNER,
    build_per_task_rows,
    compute_condition_summary,
    paired_comparison,
    validate_binding,
    write_summary,
)
from src.evaluation.io import read_json, read_jsonl  # noqa: E402

TASKS = ["synthetic/task_alpha", "synthetic/task_beta", "synthetic/task_gamma"]
CONDITIONS = ["A", "B", "C", "D"]


def load_rows():
    scored = read_jsonl(REPO_ROOT / "results" / "synthetic" / "scored_all.jsonl")
    return build_per_task_rows(scored, expected_tasks=TASKS, synthetic=True)


class AggregationTests(unittest.TestCase):
    def setUp(self):
        self.rows = load_rows()

    def test_condition_summary_hand_checkable_values(self):
        rows = self.rows
        summaries = compute_condition_summary(
            rows, expected_tasks=TASKS, conditions=CONDITIONS,
            audit_complete=True, synthetic=True,
        )
        by_condition = {s["condition"]: s for s in summaries}
        # Designed fixture: A=2/3, B=1/3, C=2/3, D=1/3 successes.
        self.assertEqual(by_condition["A"]["success_count"], 2)
        self.assertEqual(by_condition["B"]["success_count"], 1)
        self.assertEqual(by_condition["C"]["success_count"], 2)
        self.assertEqual(by_condition["D"]["success_count"], 1)
        self.assertEqual(by_condition["A"]["success_rate"], 0.6667)
        self.assertEqual(by_condition["B"]["success_rate"], 0.3333)
        # Sum all calls per task first, then average over tasks.
        # C: alpha(90) + beta(90) + gamma(90+110) = 380 -> 126.6667
        self.assertEqual(by_condition["C"]["mean_input_tokens"], 126.6667)
        self.assertEqual(by_condition["C"]["mean_output_tokens"], 10.3333)
        # A: 100 + (100+120) + 100 = 420 -> 140.0; B: 110 * 3 -> 110.0
        self.assertEqual(by_condition["A"]["mean_input_tokens"], 140.0)
        self.assertEqual(by_condition["B"]["mean_input_tokens"], 110.0)
        self.assertEqual(by_condition["B"]["mean_output_tokens"], 12.0)
        for summary in summaries:
            self.assertEqual(summary["N_expected"], 3)
            self.assertEqual(summary["N_recorded"], 3)
            self.assertEqual(summary["banner"], SYNTHETIC_BANNER)

    def test_failures_stay_in_denominator(self):
        rows = copy.deepcopy(self.rows)
        # Make every A row a failure: success_count must be 0 but N stays 3.
        for row in rows:
            if row["condition"] == "A":
                row["success"] = False
        summary = compute_condition_summary(
            rows, expected_tasks=TASKS, conditions=["A"],
            audit_complete=True, synthetic=False,
        )[0]
        self.assertEqual(summary["success_count"], 0)
        self.assertEqual(summary["N_expected"], 3)
        self.assertEqual(summary["success_rate"], 0.0)

    def test_missing_usage_is_not_zero_filled(self):
        rows = copy.deepcopy(self.rows)
        for row in rows:
            if row["condition"] == "C":
                row["input_tokens"] = None
        summary = compute_condition_summary(
            rows, expected_tasks=TASKS, conditions=["C"],
            audit_complete=True, synthetic=False,
        )[0]
        self.assertIsNone(summary["mean_input_tokens"])
        self.assertEqual(summary["n_with_usage"], 0)
        # Output tokens from the same rows are still available.
        self.assertEqual(summary["mean_output_tokens"], 10.3333)

    def test_incomplete_audit_marks_summary(self):
        rows = self.rows[:-1]  # one recorded slot missing
        summary = compute_condition_summary(
            rows, expected_tasks=TASKS, conditions=CONDITIONS,
            audit_complete=False, synthetic=False,
        )[0]
        self.assertEqual(summary["status"], "INCOMPLETE")
        self.assertIn("INCOMPLETE", summary["banner"])

    def test_paired_counts_and_interpretation(self):
        cb = paired_comparison(
            self.rows, base="C", target="B", expected_tasks=TASKS,
            synthetic=True, audit_complete=True,
        )
        self.assertEqual(cb["counts"], {
            "both_success": 1, "base_only": 1, "target_only": 0,
            "both_fail": 1, "missing_base": 0, "missing_target": 0,
        })
        self.assertIn("both", cb["interpretation"].lower())

        cd = paired_comparison(
            self.rows, base="C", target="D", expected_tasks=TASKS,
            synthetic=True, audit_complete=True,
        )
        self.assertEqual(cd["counts"]["target_only"], 1)  # gamma: D succeeds, C has no answer
        self.assertIn("filtering", cd["interpretation"].lower())

    def test_paired_missing_slot_is_explicit(self):
        rows = [r for r in self.rows if not (r["task_id"] == TASKS[0] and r["condition"] == "B")]
        pair = paired_comparison(
            rows, base="C", target="B", expected_tasks=TASKS,
            synthetic=True, audit_complete=False,
        )
        self.assertEqual(pair["counts"]["missing_target"], 1)
        self.assertTrue(any(r["outcome"] == "missing_target" for r in pair["rows"]))

    def test_write_summary_is_deterministic(self):
        audit = read_json(REPO_ROOT / "results" / "synthetic" / "audit.json")
        summaries = compute_condition_summary(
            self.rows, expected_tasks=TASKS, conditions=CONDITIONS,
            audit_complete=True, synthetic=True,
        )
        paired = {
            f"{b}_vs_{t}": paired_comparison(
                self.rows, base=b, target=t, expected_tasks=TASKS,
                synthetic=True, audit_complete=True,
            )
            for b, t in (("C", "B"), ("C", "D"))
        }
        binding = {"problems": [], "complete": True}
        with tempfile.TemporaryDirectory() as tmp:
            first = write_summary(Path(tmp) / "one", rows=self.rows,
                                  condition_summaries=summaries, paired=paired,
                                  expected_tasks=TASKS, audit_report=audit,
                                  binding=binding, complete=True,
                                  synthetic=True, conditions=CONDITIONS)
            second = write_summary(Path(tmp) / "two", rows=self.rows,
                                   condition_summaries=summaries, paired=paired,
                                   expected_tasks=TASKS, audit_report=audit,
                                   binding=binding, complete=True,
                                   synthetic=True, conditions=CONDITIONS)
            for key in ("per_task", "condition_summary", "paired_C_vs_B", "paired_C_vs_D"):
                a = Path(first[key]).read_bytes()
                b = Path(second[key]).read_bytes()
                self.assertEqual(a, b, f"non-deterministic output for {key}")


class BindingTests(unittest.TestCase):
    """summarize must not trust audit.complete; it re-binds to the scored file."""

    def setUp(self):
        self.scored = read_jsonl(REPO_ROOT / "results" / "synthetic" / "scored_all.jsonl")
        self.audit = read_json(REPO_ROOT / "results" / "synthetic" / "audit.json")

    def check(self, scored, audit=None):
        return validate_binding(
            scored, split="SYNTHETIC", conditions=CONDITIONS,
            expected_tasks=TASKS, audit_report=audit or self.audit,
        )

    def codes(self, binding):
        return [p["code"] for p in binding["problems"]]

    def test_clean_scored_binds_to_audit(self):
        binding = self.check(self.scored)
        self.assertTrue(binding["complete"])
        self.assertEqual(binding["problems"], [])

    def test_stale_audit_with_new_data_is_incomplete(self):
        new_data = copy.deepcopy(self.scored)
        new_data[0]["final_answer"] = "999"  # changed after the audit ran
        binding = self.check(new_data)
        self.assertFalse(binding["complete"])
        self.assertIn("audit_fingerprint_mismatch", self.codes(binding))

    def test_audit_without_fingerprint_is_incomplete(self):
        old_audit = {k: v for k, v in self.audit.items() if k != "input_fingerprint"}
        binding = self.check(self.scored, audit=old_audit)
        self.assertFalse(binding["complete"])
        self.assertIn("audit_missing_fingerprint", self.codes(binding))

    def test_non_boolean_success_is_incomplete(self):
        bad = copy.deepcopy(self.scored)
        bad[0]["success"] = "true"
        binding = self.check(bad)
        self.assertFalse(binding["complete"])
        self.assertIn("non_boolean_success", self.codes(binding))

    def test_duplicate_slot_cannot_exceed_100_percent(self):
        dup = copy.deepcopy(self.scored) + [copy.deepcopy(self.scored[0])]
        binding = self.check(dup)
        self.assertIn("duplicate_slot", self.codes(binding))
        rows = build_per_task_rows(dup, expected_tasks=TASKS, synthetic=True)
        summaries = compute_condition_summary(
            rows, expected_tasks=TASKS, conditions=CONDITIONS,
            audit_complete=False, synthetic=True,
        )
        for summary in summaries:
            self.assertLessEqual(summary["success_rate"], 1.0)
            self.assertLessEqual(summary["N_recorded"], 3)

    def test_missing_expected_slot_is_incomplete(self):
        short = [r for r in self.scored
                 if not (r["task_id"] == TASKS[0] and r["condition"] == "D")]
        binding = self.check(short)
        self.assertFalse(binding["complete"])
        self.assertIn("missing_slot", self.codes(binding))

    def test_run_identity_mismatch_detected(self):
        bad = copy.deepcopy(self.scored)
        for record in bad:
            record["run_id"] = "a-different-run"
        binding = self.check(bad)
        self.assertIn("run_identity_mismatch", self.codes(binding))

    def test_config_identity_mismatch_detected(self):
        bad = copy.deepcopy(self.scored)
        bad[0]["config_sha256"] = "a-different-config"
        binding = self.check(bad)
        self.assertIn("config_identity_mismatch", self.codes(binding))


if __name__ == "__main__":
    unittest.main()
