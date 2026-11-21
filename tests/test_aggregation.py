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
        # Sum all calls per task first (C: 90+110=200), then average over tasks.
        self.assertEqual(by_condition["C"]["mean_input_tokens"], 200.0)
        self.assertEqual(by_condition["C"]["mean_output_tokens"], 13.0)
        self.assertEqual(by_condition["A"]["mean_input_tokens"], 220.0)
        self.assertEqual(by_condition["B"]["mean_output_tokens"], 18.0)
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
        self.assertEqual(summary["mean_output_tokens"], 13.0)

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
        with tempfile.TemporaryDirectory() as tmp:
            first = write_summary(Path(tmp) / "one", rows=self.rows,
                                  condition_summaries=summaries, paired=paired,
                                  expected_tasks=TASKS, audit_report=audit,
                                  synthetic=True, conditions=CONDITIONS)
            second = write_summary(Path(tmp) / "two", rows=self.rows,
                                   condition_summaries=summaries, paired=paired,
                                   expected_tasks=TASKS, audit_report=audit,
                                   synthetic=True, conditions=CONDITIONS)
            for key in ("per_task", "condition_summary", "paired_C_vs_B", "paired_C_vs_D"):
                a = Path(first[key]).read_bytes()
                b = Path(second[key]).read_bytes()
                self.assertEqual(a, b, f"non-deterministic output for {key}")


if __name__ == "__main__":
    unittest.main()
