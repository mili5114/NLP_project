"""C-owned integration checks for the A runtime handoff (CPU only)."""
import json
import tempfile
import unittest
from pathlib import Path

from src.runtime.backend import FakeBackend
from src.runtime.config import load_course_config
from src.runtime.runner import run_episode
from src.evaluation.turns_reader import read_turns
from src.evaluation.tool_audit import audit_tool_attempts


class ToolBudgetHandoffTest(unittest.TestCase):
    def run_case(self, final_reply):
        cfg = load_course_config()
        temporary = tempfile.TemporaryDirectory(prefix="c-handoff-")
        self.addCleanup(temporary.cleanup)
        code = "for _ in range(32):\n    find_flights('E', 'A', '2023-12-25')\nprint('block completed')"
        backend = FakeBackend(replies=[f"Action:\n{code}\nEnd Action", final_reply,
                                       "Answer: should never be reached"], stop_text=cfg.stop_text)
        result = run_episode(task_id="travel_itinerary_planning/cheapest_new_york_trip",
                             condition="A", cfg=cfg, backend=backend,
                             runs_root=temporary.name, split="DEV")
        raw = [json.loads(line) for line in Path(result["turns_path"]).read_text(encoding="utf-8").splitlines()]
        turns = read_turns(result["turns_path"])
        check = audit_tool_attempts(turns, {"tool_attempts_per_action": 4, "tool_attempts_per_task": 32})
        self.assertEqual((check["attempted"], check["executed"], check["blocked"]), (32, 4, 28))
        self.assertEqual(check["issues"], [])
        self.assertEqual(backend.calls, 2)
        self.assertEqual(len(raw), 2)
        self.assertIn("block completed", raw[0]["python_output"])
        self.assertTrue(turns[-1]["is_final_answer_turn"])
        self.assertEqual(raw[-1]["generation_settings"]["max_new_tokens"], 128)
        self.assertEqual(raw[-1]["events"], [])
        return result["episode"]

    def test_blocked_attempts_trigger_final_with_only_four_executions(self):
        episode = self.run_case("Answer: ok")
        self.assertEqual(episode["termination_reason"], "final_answer_after_tool_budget_exhausted")
        self.assertEqual(episode["final_answer"], "ok")

    def test_action_in_reserved_final_is_not_executed(self):
        episode = self.run_case("Action:\nfind_flights('E', 'A', '2023-12-25')\nEnd Action")
        self.assertEqual(episode["termination_reason"], "no_answer_after_tool_budget_exhausted")
        self.assertIsNone(episode["final_answer"])
