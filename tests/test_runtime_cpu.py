"""CPU 上的平台验收测试（不需要 GPU）。

用 FakeBackend 脚本化模型输出，验证课程规则里最容易做错的几件事：
- 首个可解析 Answer 立即结束；
- 块内 4 次、任务 32 次的工具计数，超限不执行但保留前面效果；
- 12 轮用尽后只发一次禁工具的最终轮；
- 没有答案时 final_answer 为 null，episode 仍然落盘；
- 任务之间变量与工具状态重置；
- 在线记录里不出现标准答案。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.feedback.baselines import feedback_official_output, feedback_trace_first
from src.runtime.backend import FakeBackend
from src.runtime.config import load_course_config
from src.runtime.runner import run_episode

TASK = "travel_itinerary_planning/cheapest_new_york_trip"
SETTINGS = {
    "feedback_characters": 2000,
    "truncation_marker": "\n[Output Truncated]",
    "full_trace_format": {
        "prefix": "Tool execution trace (actual calls, in execution order):\n",
        "event": "[{index}] {tool} args={args_repr} kwargs={kwargs_repr} [{execution_status}] -> {result_or_error}",
        "python_separator": "\nPython output:\n",
    },
}


def action(code: str) -> str:
    return f"Action:\n{code}\nEnd Action"


class EpisodeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cfg = load_course_config()

    def run_episode(self, replies: list[str], *, condition: str = "A", task: str = TASK):
        tmp = tempfile.mkdtemp(prefix="nlp-test-")
        backend = FakeBackend(replies=replies, stop_text=self.cfg.stop_text)
        result = run_episode(
            task_id=task,
            condition=condition,
            cfg=self.cfg,
            backend=backend,
            runs_root=tmp,
            split="DEV",
        )
        return result, Path(tmp), backend

    # ---------- 终止语义 ----------
    def test_first_answer_stops_immediately(self) -> None:
        result, root, backend = self.run_episode(["Answer: 450"])
        ep = result["episode"]
        self.assertEqual(ep["termination_reason"], "answer")
        self.assertEqual(ep["final_answer"], "450")
        self.assertEqual(ep["model_calls"], 1)
        self.assertEqual(ep["tool_attempts_executed"], 0)
        self.assertEqual(backend.calls, 1)

    def test_action_then_answer(self) -> None:
        result, _root, _backend = self.run_episode(
            [
                action("price = find_flights('E', 'A', '2023-12-25')[0]['price']\nprint(price)"),
                "Answer: 450",
            ]
        )
        ep = result["episode"]
        self.assertEqual(ep["termination_reason"], "answer")
        self.assertEqual(ep["model_calls"], 2)
        self.assertEqual(ep["tool_attempts_executed"], 1)
        self.assertEqual(ep["tool_attempts_blocked"], 0)

    def test_turn_budget_exhausted_then_final_answer(self) -> None:
        replies = [action("print('thinking')")] * self.cfg.limits.interaction_turns + ["Answer: 42"]
        result, _root, backend = self.run_episode(replies)
        ep = result["episode"]
        self.assertEqual(ep["termination_reason"], "final_answer_after_turns_exhausted")
        self.assertEqual(ep["final_answer"], "42")
        self.assertEqual(ep["model_calls"], self.cfg.limits.interaction_turns + 1)
        self.assertEqual(backend.calls, self.cfg.limits.interaction_turns + 1)

    def test_no_answer_records_null(self) -> None:
        replies = [action("print('thinking')")] * (self.cfg.limits.interaction_turns + 5)
        result, root, _backend = self.run_episode(replies)
        ep = result["episode"]
        self.assertEqual(ep["status"], "no_answer")
        self.assertIsNone(ep["final_answer"])
        self.assertTrue(ep["termination_reason"].startswith("no_answer_after_"))
        # episode 仍然落盘
        self.assertTrue((root / "DEV" / "A").exists())
        self.assertTrue(Path(result["episode_path"]).exists())

    def test_final_turn_executes_no_tools(self) -> None:
        """最终轮即使输出 Action 也不能执行工具。"""
        replies = [action("print('x')")] * self.cfg.limits.interaction_turns
        replies.append(action("find_flights('E', 'A', '2023-12-25')"))
        result, _root, _backend = self.run_episode(replies)
        ep = result["episode"]
        self.assertIsNone(ep["final_answer"])
        # 12 个交互轮各 0 次工具 + 最终轮被禁止 → 仍是 0
        self.assertEqual(ep["tool_attempts_executed"], 0)

    # ---------- 工具计数 ----------
    def test_fifth_call_in_block_is_blocked(self) -> None:
        code = "find_flights('E', 'A', '2023-12-25')\n" * 5 + "print('done')"
        result, _root, _backend = self.run_episode([action(code), "Answer: ok"])
        ep = result["episode"]
        self.assertEqual(ep["tool_attempts_executed"], 4)
        self.assertEqual(ep["tool_attempts_blocked"], 1)

    def test_blocked_call_keeps_earlier_effects(self) -> None:
        code = (
            "a = find_flights('E', 'A', '2023-12-25')\n"
            "b = find_flights('E', 'A', '2023-12-25')\n"
            "c = find_flights('E', 'A', '2023-12-25')\n"
            "d = find_flights('E', 'A', '2023-12-25')\n"
            "e = find_flights('E', 'A', '2023-12-25')\n"
            "print('a_ok=', a is not None, 'b_ok=', b is not None, 'e_is_none=', e is None)"
        )
        result, root, _backend = self.run_episode([action(code), "Answer: ok"])
        turns = (root / "DEV" / "A" / Path(result["turns_path"]).parent.name / "turns.jsonl")
        first = json.loads(turns.read_text(encoding="utf-8").splitlines()[0])
        self.assertIn("a_ok= True", first["python_output"])
        self.assertIn("b_ok= True", first["python_output"])
        self.assertIn("e_is_none= True", first["python_output"])
        self.assertEqual(first["tool_events"][-1]["execution_status"], "blocked")

    def test_task_level_limit_32(self) -> None:
        code = "find_flights('E', 'A', '2023-12-25')\n" * 4
        replies = [action(code)] * 8 + [action("find_flights('E', 'A', '2023-12-25')"), "Answer: ok"]
        result, _root, _backend = self.run_episode(replies)
        ep = result["episode"]
        self.assertEqual(ep["tool_attempts_executed"], 32)
        self.assertEqual(ep["tool_attempts_blocked"], 1)

    # ---------- 状态隔离 ----------
    def test_variables_reset_between_tasks(self) -> None:
        result1, _r1, _b1 = self.run_episode([action("secret = 123\nprint(secret)"), "Answer: 1"])
        self.assertEqual(result1["episode"]["status"], "completed")

        result2, root2, _b2 = self.run_episode([action("print(secret)"), "Answer: 2"])
        turns = Path(result2["turns_path"])
        first = json.loads(turns.read_text(encoding="utf-8").splitlines()[0])
        self.assertIn("NameError", first["python_output"])
        self.assertEqual(result2["episode"]["status"], "completed")

    # ---------- 记录里不能有答案 ----------
    def test_no_reference_leak(self) -> None:
        result, root, _backend = self.run_episode([action("print('x')"), "Answer: 450"])
        episode_dir = Path(result["episode_path"]).parent
        for path in episode_dir.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("expected_output", text, msg=f"{path.name} 泄漏了字段名")
                self.assertNotIn("Expected Output", text, msg=f"{path.name} 泄漏了标准答案打印")
                self.assertNotIn("is_correct", text)

    def test_turn_records_have_real_usage(self) -> None:
        result, _root, _backend = self.run_episode([action("print(1)"), "Answer: 3"])
        lines = Path(result["turns_path"]).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        for line in lines:
            rec = json.loads(line)
            self.assertGreater(rec["input_tokens"], 0)
            self.assertIn("budget", rec)
            self.assertIn("messages", rec)
        ep = result["episode"]
        self.assertEqual(
            ep["input_tokens"], sum(json.loads(x)["input_tokens"] for x in lines)
        )


class FeedbackTest(unittest.TestCase):
    def test_condition_a_returns_python_output_verbatim(self) -> None:
        out = "hello\nworld"
        res = feedback_official_output(python_output=out, events=[], settings=SETTINGS)
        self.assertEqual(res["text"], out)
        self.assertEqual(res["metadata"]["feedback_chars"], len(out))

    def test_condition_b_puts_trace_first(self) -> None:
        events = [
            {
                "index": 1,
                "tool": "find_flights",
                "args_repr": "'E', 'A'",
                "kwargs_repr": "",
                "execution_status": "ok",
                "result_repr": "[{'price': 450}]",
                "error_repr": None,
                "elapsed_seconds": 0.001,
            }
        ]
        res = feedback_trace_first(python_output="450", events=events, settings=SETTINGS)
        self.assertTrue(res["text"].startswith("Tool execution trace"))
        self.assertIn("[1] find_flights", res["text"])
        self.assertIn("Python output:", res["text"])
        self.assertLessEqual(len(res["text"]), 2000)

    def test_condition_b_respects_2000_limit(self) -> None:
        events = [
            {
                "index": i,
                "tool": "t",
                "args_repr": "x" * 300,
                "kwargs_repr": "",
                "execution_status": "ok",
                "result_repr": "y" * 300,
                "error_repr": None,
                "elapsed_seconds": 0.0,
            }
            for i in range(1, 11)
        ]
        res = feedback_trace_first(python_output="z" * 5000, events=events, settings=SETTINGS)
        self.assertLessEqual(len(res["text"]), 2000)
        self.assertTrue(res["metadata"]["truncated"])
        self.assertTrue(res["metadata"]["omitted_event_indices"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
