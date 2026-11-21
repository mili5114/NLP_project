"""Meaningful boundary tests for the offline scorer.

Expected values are written by hand; the function under test is never used to
generate its own expectations.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.errors import DataError  # noqa: E402
from src.evaluation.scoring import (  # noqa: E402
    REASON_CORRECT,
    REASON_NONFINITE_PREDICTION,
    REASON_NO_ANSWER,
    REASON_UNPARSEABLE_PREDICTION,
    score_episode,
)


def episode_with(answer, **overrides):
    record = {
        "task_id": "synthetic/t",
        "split": "SYNTHETIC",
        "synthetic": True,
        "condition": "C",
        "final_answer": answer,
        "termination_reason": "first_parseable_answer",
    }
    record.update(overrides)
    return record


def score(answer, reference, answer_type="numeric", **overrides):
    return score_episode(episode_with(answer, **overrides),
                         reference=reference, answer_type=answer_type)


class NumericScoringTests(unittest.TestCase):
    def test_exact_and_within_tolerance(self):
        for pred, ref in [("42", "42"), ("1.0000001", "1.0"), ("0.3", "0.3000005")]:
            with self.subTest(pred=pred, ref=ref):
                result = score(pred, ref)
                self.assertIs(result["success"], True)
                self.assertEqual(result["scoring_reason"], REASON_CORRECT)

    def test_tolerance_boundaries(self):
        # 1e-6 exactly -> correct; just above -> wrong.  Written by hand.
        self.assertIs(score("1.000001", "1.000000")["success"], True)
        self.assertIs(score("1.0000011", "1.000000")["success"], False)

    def test_negative_and_scientific_notation(self):
        self.assertIs(score("-12.5", "-12.5")["success"], True)
        self.assertIs(score("1e3", "1000")["success"], True)
        self.assertIs(score("-2.5E-2", "-0.025")["success"], True)

    def test_high_precision_not_rounded_by_decimal_default(self):
        a = "0.123456789012345678901234567890"
        b = "0.123456789012345678901234567891"  # diff = 1e-30
        self.assertIs(score(a, b)["success"], True)
        c = "0.1234567890123456789012345678901"
        self.assertIs(score(a, c)["success"], True)

    def test_large_numbers(self):
        big = "1234567890123456789012345678901234567890"
        self.assertIs(score(big, big)["success"], True)
        self.assertIs(score(big, big + "1")["success"], False)

    def test_no_float_conversion_artifact(self):
        # In float, 0.1 + 0.2 == 0.30000000000000004.  Decimal string parsing
        # must treat these as a within-tolerance match, not a mismatch.
        self.assertIs(score("0.30000000000000004", "0.3")["success"], True)

    def test_nan_infinity_and_unparseable_prediction_are_failures(self):
        for pred, reason in [("NaN", REASON_NONFINITE_PREDICTION),
                             ("Infinity", REASON_NONFINITE_PREDICTION),
                             ("-inf", REASON_NONFINITE_PREDICTION),
                             ("not-a-number", REASON_UNPARSEABLE_PREDICTION)]:
            with self.subTest(pred=pred):
                result = score(pred, "1.0")
                self.assertIs(result["success"], False)
                self.assertEqual(result["scoring_reason"], reason)

    def test_bad_reference_is_a_data_error(self):
        for ref in ["NaN", "Infinity", "abc", None, True]:
            with self.subTest(ref=ref), self.assertRaises(DataError):
                score("1.0", ref)

    def test_no_answer_still_validates_reference(self):
        # A null prediction must NOT short-circuit past reference validation:
        # a corrupt reference is a data error, not a silent model failure.
        for ref in ["NaN", "Infinity", "abc", None, ""]:
            with self.subTest(ref=ref), self.assertRaises(DataError):
                score(None, ref, "numeric")
        with self.subTest(ref="non-string"), self.assertRaises(DataError):
            score(None, 42, "string")


class StringScoringTests(unittest.TestCase):
    def test_strip_only_not_case_or_internal_space(self):
        self.assertIs(score("  hello ", "hello", "string")["success"], True)
        self.assertIs(score("hello world", "hello  world", "string")["success"], False)
        self.assertIs(score("Hello", "hello", "string")["success"], False)

    def test_trailing_newline_and_punctuation_kept(self):
        self.assertIs(score("a@b.com\n", "a@b.com", "string")["success"], True)
        self.assertIs(score("a@b.com.", "a@b.com", "string")["success"], False)

    def test_non_string_reference_is_data_error(self):
        with self.assertRaises(DataError):
            score("x", 42, "string")


class FailureAndSafetyTests(unittest.TestCase):
    def test_null_answer_is_recorded_failure_with_reason_preserved(self):
        result = score(None, "42", termination_reason="budget_exhausted")
        self.assertIs(result["success"], False)
        self.assertEqual(result["scoring_reason"], REASON_NO_ANSWER)
        self.assertEqual(result["termination_reason"], "budget_exhausted")
        self.assertIn("final_answer", result)

    def test_unknown_answer_type_is_data_error(self):
        with self.assertRaises(DataError):
            score("1", "1", "json")

    def test_episode_not_mutated_and_reference_not_leaked(self):
        ep = episode_with("42")
        result = score_episode(ep, reference="42", answer_type="numeric")
        self.assertNotIn("reference", result)
        self.assertNotIn("expected_success", result)
        self.assertEqual(ep["final_answer"], "42")
        self.assertNotIn("success", ep)

    def test_answer_type_is_not_guessed_from_prediction(self):
        # "42" looks numeric but a string reference means exact string match.
        self.assertIs(score("42", "042", "string")["success"], False)


if __name__ == "__main__":
    unittest.main()
