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
CONDITION_SHAS = {c: f"synthetic-config-{c}-sha" for c in "ABCD"}


def load_fixture_set():
    index = read_jsonl(FIXTURES / "index.jsonl")
    episodes = [read_json(FIXTURES / row["episode_path"]) for row in index]
    tasks = read_json(FIXTURES / "tasks.json")
    settings = read_json(REPO_ROOT / "configs" / "course" / "runtime_settings.json")
    return episodes, tasks, settings


def codes(report, key="errors"):
    return [item["code"] for item in report[key]]


def make_turn(index, *, output_tokens, produced=False, final_only=False, events=None):
    return {
        "turn_index": index,
        "is_final_answer_turn": final_only,
        "produced_final_answer": produced,
        "messages": [{"role": "user", "content": "SYNTHETIC"}],
        "raw_model_text": "Answer: 1",
        "events": events if events is not None else [],
        "feedback": None,
        "input_tokens": 10,
        "output_tokens": output_tokens,
        "wall_seconds": 0.1,
    }


def write_case(tmp, turns, *, answer="1", task="synthetic/only", extra_ep=None):
    turns_path = Path(tmp) / "turns.jsonl"
    turns_path.write_text("".join(json.dumps(t) + "\n" for t in turns), encoding="utf-8")
    ep = {
        "synthetic": True,
        "run_id": "synthetic-case",
        "task_id": task,
        "split": "SYNTHETIC",
        "condition": "A",
        "status": "finished",
        "termination_reason": "first_parseable_answer",
        "final_answer": answer,
        "input_tokens": sum(t["input_tokens"] for t in turns),
        "output_tokens": sum(t["output_tokens"] for t in turns),
        "model_calls": len(turns),
        "tool_attempts_executed": 0,
        "tool_attempts_blocked": 0,
        "wall_seconds": 1.0,
        "trajectory_path": str(turns_path),
        "config_sha256": CONDITION_SHAS["A"],
    }
    if extra_ep:
        ep.update(extra_ep)
    return ep


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
            condition_config_shas=CONDITION_SHAS,
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
        self.assertTrue(report["input_fingerprint"])

    def test_per_condition_hashes_may_differ(self):
        report = self.run_audit()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(len({v[0] for v in report["config_by_condition"].values()}), 4)

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


class FinalAnswerSemanticsTests(unittest.TestCase):
    """Interaction-answer turns (384 cap) vs final-only turns (128 cap)."""

    def setUp(self):
        self.settings = read_json(REPO_ROOT / "configs" / "course" / "runtime_settings.json")

    def run_case(self, turns, *, answer="1", task="synthetic/only"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ep = write_case(tmp.name, turns, answer=answer, task=task)
        return audit_episodes(
            [ep], split="SYNTHETIC", conditions=["A"], settings=self.settings,
            allow_synthetic=True, synthetic_tasks=[task],
            condition_config_shas={"A": CONDITION_SHAS["A"]},
        )

    def test_interaction_turn_can_answer_with_384_limit(self):
        # Answer produced inside an interaction turn at 300 tokens: valid.
        report = self.run_case([make_turn(1, output_tokens=300, produced=True)])
        self.assertEqual(report["status"], "PASS")
        self.assertNotIn("turn_token_limit_exceeded", codes(report))

    def test_interaction_answer_over_384_is_rejected(self):
        report = self.run_case([make_turn(1, output_tokens=385, produced=True)])
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("turn_token_limit_exceeded", codes(report))

    def test_final_only_turn_over_128_is_rejected(self):
        turns = [make_turn(1, output_tokens=10, produced=False),
                 make_turn(2, output_tokens=200, final_only=True)]
        report = self.run_case(turns, answer=None)
        self.assertIn("turn_token_limit_exceeded", codes(report))

    def test_tools_do_not_execute_in_final_only_turn(self):
        turns = [make_turn(1, output_tokens=10, produced=False),
                 make_turn(2, output_tokens=10, final_only=True,
                           events=[{"index": 1, "tool": "x"}])]
        report = self.run_case(turns, answer=None)
        self.assertIn("tool_in_final_answer_turn", codes(report))

    def test_answer_without_produced_turn_is_rejected(self):
        report = self.run_case([make_turn(1, output_tokens=10, produced=False)], answer="1")
        self.assertIn("final_answer_call_missing", codes(report))

    def test_produced_turn_without_answer_is_rejected(self):
        report = self.run_case([make_turn(1, output_tokens=10, produced=True)], answer=None)
        self.assertIn("answer_state_mismatch", codes(report))

    def test_clean_interaction_answer_passes(self):
        report = self.run_case([make_turn(1, output_tokens=10, produced=True)], answer="1")
        self.assertEqual(report["status"], "PASS")


class ToolCounterIntegrationTests(unittest.TestCase):
    def run_case(self, statuses, executed, blocked, final_only=True):
        with tempfile.TemporaryDirectory() as tmp:
            events = [{"index": i, "execution_status": s, "result_repr": None}
                      for i, s in enumerate(statuses, 1)]
            turns = [make_turn(1, output_tokens=10, events=events),
                     make_turn(2, output_tokens=10, produced=True, final_only=final_only)]
            ep = write_case(tmp, turns, extra_ep={"tool_attempts_executed": executed,
                                                "tool_attempts_blocked": blocked})
            settings = read_json(REPO_ROOT / "configs/course/runtime_settings.json")
            return audit_episodes([ep], split="SYNTHETIC", conditions=["A"],
                                  allow_synthetic=True, synthetic_tasks=["synthetic/only"],
                                  settings=settings)

    def test_legal_blocked_attempts_do_not_fail_audit(self):
        report = self.run_case(["ok"] * 4 + ["blocked"] * 35, 4, 35)
        self.assertEqual(codes(report), [])
        self.assertEqual(report["status"], "PASS")

    def test_interaction_after_task_budget_is_rejected(self):
        report = self.run_case(["ok"] * 4 + ["blocked"] * 35, 4, 35, final_only=False)
        self.assertIn("interaction_after_tool_budget_exhausted", codes(report))
        self.assertFalse(report["complete"])

    def test_counters_must_match_events(self):
        report = self.run_case(["ok", "error"], 1, 0)
        self.assertIn("tool_counter_mismatch", codes(report))

    def test_unblocked_fifth_call_fails(self):
        report = self.run_case(["ok"] * 5, 5, 0)
        self.assertIn("unblocked_over_budget_tool", codes(report))


class FormalVersionTests(unittest.TestCase):
    """Formal audits must verify versions instead of skipping absent fields."""

    def setUp(self):
        self.settings = read_json(REPO_ROOT / "configs" / "course" / "runtime_settings.json")
        self.manifest = {"DEV": ["dev/task"], "EVAL": ["eval/task"]}

    def test_formal_mode_requires_version_expectations(self):
        report = audit_episodes(
            [], split="DEV", conditions=["A"], manifest=self.manifest,
            settings=self.settings, allow_synthetic=False,
        )
        self.assertIn("formal_version_expectation_missing", codes(report))
        self.assertNotEqual(report["status"], "PASS")

    def test_formal_episode_missing_config_sha_fails(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ep = write_case(tmp.name, [make_turn(1, output_tokens=10, produced=True)],
                        answer="1", task="dev/task")
        ep.update({"synthetic": False, "split": "DEV", "code_commit": "c0",
                   "model_revision": "r0"})
        del ep["config_sha256"]
        report = audit_episodes(
            [ep], split="DEV", conditions=["A"], manifest=self.manifest,
            settings=self.settings, allow_synthetic=False,
            condition_config_shas={"A": "sha-a"},
            expected_code_commit="c0", expected_model_revision="r0",
        )
        self.assertIn("config_sha256_missing", codes(report))
        self.assertNotEqual(report["status"], "PASS")

    def test_formal_per_condition_hash_mismatch_fails(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ep = write_case(tmp.name, [make_turn(1, output_tokens=10, produced=True)],
                        answer="1", task="dev/task")
        ep.update({"synthetic": False, "split": "DEV", "code_commit": "c0",
                   "model_revision": "r0", "config_sha256": "wrong"})
        report = audit_episodes(
            [ep], split="DEV", conditions=["A"], manifest=self.manifest,
            settings=self.settings, allow_synthetic=False,
            condition_config_shas={"A": "sha-a"},
            expected_code_commit="c0", expected_model_revision="r0",
        )
        self.assertIn("config_hash_mismatch", codes(report))


class TurnsReaderTests(unittest.TestCase):
    def test_usage_separates_the_two_final_concepts(self):
        # alpha_C answers inside the interaction turn: 1 call, produced=[1], no final-only.
        turns = read_turns(FIXTURES / "turns" / "task_alpha_C.jsonl")
        usage = summarize_turn_usage(turns)
        self.assertEqual(usage["model_calls"], 1)
        self.assertEqual(usage["input_tokens"], 90)
        self.assertEqual(usage["output_tokens"], 9)
        self.assertEqual(usage["final_answer_turns"], [1])
        self.assertEqual(usage["final_only_turns"], [])

    def test_final_only_turn_is_distinct(self):
        # beta_A has no answer; turn 2 is the dedicated final-only turn.
        turns = read_turns(FIXTURES / "turns" / "task_beta_A.jsonl")
        usage = summarize_turn_usage(turns)
        self.assertEqual(usage["model_calls"], 2)
        self.assertEqual(usage["final_only_turns"], [2])
        self.assertEqual(usage["final_answer_turns"], [])

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
