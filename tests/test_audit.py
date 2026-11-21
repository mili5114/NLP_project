"""Tests for completeness auditing and the turns reader adapter."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.audit import audit_episodes, load_manifest  # noqa: E402
from src.evaluation.errors import InputError  # noqa: E402
from src.evaluation.io import read_json, read_jsonl  # noqa: E402
from src.evaluation.turns_reader import read_turns, summarize_turn_usage  # noqa: E402

FIXTURES = REPO_ROOT / "fixtures" / "evaluation"


def load_fixture_set():
    index = read_jsonl(FIXTURES / "index.jsonl")
    episodes = [read_json(FIXTURES / row["episode_path"]) for row in index]
    tasks = read_json(FIXTURES / "tasks.json")
    settings = read_json(REPO_ROOT / "configs" / "course" / "runtime_settings.json")
    return episodes, tasks, settings


def codes(report, key="errors"):
    return [item["code"] for item in report[key]]


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.episodes, self.tasks, self.settings = load_fixture_set()

    def run_audit(self, episodes=None, **overrides):
        kwargs = dict(
            split="SYNTHETIC",
            conditions=["A", "B", "C", "D"],
            settings=self.settings,
            allow_synthetic=True,
            synthetic_tasks=self.tasks,
            trajectory_root=REPO_ROOT,
            expected_config_sha="synthetic-config-sha-placeholder",
        )
        kwargs.update(overrides)
        return audit_episodes(episodes if episodes is not None else self.episodes, **kwargs)

    def test_clean_synthetic_set_passes(self):
        report = self.run_audit()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["expected_slot_count"], 12)
        self.assertEqual(report["recorded_slot_count"], 12)
        self.assertEqual(report["errors"], [])
        self.assertEqual(len(report["recorded_failures"]), 2)  # no_answer + budget_exhausted

    def test_missing_slot_is_not_silently_dropped(self):
        report = self.run_audit(self.episodes[:-1])
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("missing_slot", codes(report))
        self.assertEqual(len(report["missing_slots"]), 1)

    def test_duplicate_slot_detected(self):
        dup = copy.deepcopy(self.episodes) + [copy.deepcopy(self.episodes[0])]
        report = self.run_audit(dup)
        self.assertIn("duplicate_slot", codes(report))
        self.assertIn("synthetic/task_alpha|A", report["duplicate_slots"])

    def test_unknown_task_and_wrong_split_and_condition(self):
        bad = copy.deepcopy(self.episodes)
        bad[0]["task_id"] = "synthetic/not_in_list"
        bad[1]["split"] = "EVAL"
        bad[2]["condition"] = "Z"
        report = self.run_audit(bad)
        self.assertIn("unknown_task", codes(report))
        self.assertIn("wrong_split", codes(report))
        self.assertIn("condition_not_requested", codes(report))

    def test_token_total_mismatch_detected(self):
        bad = copy.deepcopy(self.episodes)
        bad[0]["output_tokens"] = 999
        report = self.run_audit(bad)
        self.assertIn("token_total_mismatch", codes(report))

    def test_model_call_count_mismatch_detected(self):
        bad = copy.deepcopy(self.episodes)
        bad[0]["model_calls"] = 7
        report = self.run_audit(bad)
        self.assertIn("model_call_count_mismatch", codes(report))

    def test_config_hash_mismatch_detected(self):
        bad = copy.deepcopy(self.episodes)
        bad[0]["config_sha256"] = "wrong-hash"
        report = self.run_audit(bad)
        self.assertIn("config_hash_mismatch", codes(report))

    def test_formal_mode_rejects_synthetic_contamination(self):
        manifest = load_manifest(REPO_ROOT / "configs" / "course" / "split_manifest.json")
        report = audit_episodes(
            self.episodes, split="DEV", conditions=["A", "B"],
            manifest=manifest, settings=self.settings, allow_synthetic=False,
            trajectory_root=REPO_ROOT,
        )
        self.assertIn("synthetic_contamination", codes(report))

    def test_eval_expected_108_slots(self):
        manifest = load_manifest(REPO_ROOT / "configs" / "course" / "split_manifest.json")
        self.assertEqual(len(manifest["DEV"]), 16)
        self.assertEqual(len(manifest["EVAL"]), 27)
        with self.assertRaises(InputError):
            audit_episodes(
                [], split="EVAL", conditions=["A", "B", "C", "D"],
                manifest={"DEV": manifest["DEV"], "EVAL": manifest["EVAL"][:5]},
                settings=self.settings, allow_synthetic=False,
            )

    def test_synthetic_mode_requires_explicit_task_list(self):
        with self.assertRaises(InputError):
            audit_episodes(
                self.episodes, split="SYNTHETIC", conditions=["A"],
                settings=self.settings, allow_synthetic=True, synthetic_tasks=None,
            )


class TurnsReaderTests(unittest.TestCase):
    def test_usage_sums_all_calls_and_includes_final(self):
        path = FIXTURES / "turns" / "task_alpha_C.jsonl"
        turns = read_turns(path)
        usage = summarize_turn_usage(turns)
        self.assertEqual(usage["model_calls"], 2)
        self.assertEqual(usage["input_tokens"], 200)  # 90 + 110
        self.assertEqual(usage["output_tokens"], 13)  # 9 + 4
        self.assertEqual(usage["final_answer_turns"], [2])

    def test_missing_usage_is_flagged_not_zero_filled(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "turns.jsonl"
            turns = read_jsonl(FIXTURES / "turns" / "task_alpha_C.jsonl")
            del turns[0]["input_tokens"]
            path.write_text("".join(json.dumps(t) + "\n" for t in turns), encoding="utf-8")
            usage = summarize_turn_usage(read_turns(path))
            self.assertIsNone(usage["input_tokens"])
            self.assertEqual(usage["missing_usage_turns"], [1])

    def test_malformed_turns_line_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "turns.jsonl"
            path.write_text('{"turn_index": 1}\n', encoding="utf-8")
            with self.assertRaises(InputError):
                read_turns(path)


if __name__ == "__main__":
    unittest.main()
