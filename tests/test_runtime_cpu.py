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

import dataclasses
import json
import tempfile
import time
import unittest
from pathlib import Path

from src.feedback.baselines import feedback_official_output, feedback_trace_first
from src.runtime.backend import FakeBackend, Generation
from src.runtime.config import load_course_config
from src.runtime.runner import build_system_prompt, run_episode
from src.runtime.tasks import get_task

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


class DeadlineBackend(FakeBackend):
    """模拟慢模型：一次生成跨过任务截止时刻，返回 finish_reason=deadline。

    真实后端用 Transformers 的 StoppingCriteria 在 180s 处截断；这里用 sleep 把
    task_seconds 缩到 0.2s，复现同一语义（不必占 GPU）。
    """

    def __init__(self, *, delay: float, **kwargs) -> None:
        super().__init__(**kwargs)
        self.delay = delay

    def generate(self, messages, *, max_new_tokens: int, deadline: float | None = None):
        time.sleep(self.delay)
        gen = super().generate(messages, max_new_tokens=max_new_tokens, deadline=deadline)
        cut = deadline is not None and time.monotonic() >= deadline
        return Generation(
            text=gen.text,
            prompt_tokens=gen.prompt_tokens,
            completion_tokens=gen.completion_tokens,
            elapsed_seconds=self.delay,
            hit_stop=gen.hit_stop,
            finish_reason="deadline" if cut else gen.finish_reason,
        )


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

    def test_reserved_final_turn_used_when_token_budget_low(self) -> None:
        """生成预算只剩为最终轮预留的 128 时，必须进最终轮而不是直接判耗尽。

        复现 PR #3 审查发现的问题：optimizing_bulk_purchase_discounts A/B
        终止于 token_budget_exhausted，预留的 128 token 没有进入最终回答轮。
        """
        # 每轮回复在 stop 截断后恰好 368 字符（"Action:\n" + 360）→ 每轮计费 368 token
        filler = "# " + "x" * 358
        self.assertEqual(len("Action:\n" + filler), 368)
        replies = [action(filler)] * 8 + ["Answer: 42"]
        result, _root, backend = self.run_episode(replies)
        ep = result["episode"]
        self.assertEqual(ep["termination_reason"], "final_answer_after_tokens_exhausted")
        self.assertEqual(ep["final_answer"], "42")
        # 8 个交互轮 + 1 个最终轮；旧逻辑会在第 9 次分配前直接终止（只有 8 次调用）
        self.assertEqual(ep["model_calls"], 9)
        self.assertEqual(backend.calls, 9)
        lines = Path(result["turns_path"]).read_text(encoding="utf-8").splitlines()
        last = json.loads(lines[-1])
        self.assertTrue(last["generation_settings"]["is_final_turn"])
        self.assertEqual(last["generation_settings"]["max_new_tokens"], 128)

    def test_generate_receives_task_deadline(self) -> None:
        """每次 generate 都带上任务 180s 截止时刻（后端在生成中途截断用）。"""
        result, _root, backend = self.run_episode(
            [action("print('x')"), "Answer: ok"]
        )
        self.assertEqual(result["episode"]["termination_reason"], "answer")
        self.assertEqual(len(backend.seen_deadlines), backend.calls)
        self.assertTrue(all(d is not None for d in backend.seen_deadlines))
        self.assertEqual(len(set(backend.seen_deadlines)), 1)  # 同一集内截止时刻不变
        # 截止时刻 = episode 起点 + task_seconds，必然在未来一点的位置
        self.assertGreater(backend.seen_deadlines[0], 0)

    def _short_task_cfg(self, seconds: float):
        raw = {**self.cfg.raw, "limits": {**self.cfg.raw["limits"], "task_seconds": seconds}}
        return dataclasses.replace(self.cfg, raw=raw)

    def test_deadline_cut_records_generation_stop_and_persist_separately(self) -> None:
        """180s 到点截断：这一轮照常落盘，但不执行动作、不进最终轮。

        同时验证日志能把"生成停止"和"最终落盘"分开（课程 180s 是任务截止，
        185s 只是含停止/同步/落盘的工程检查线）。
        """
        cfg = self._short_task_cfg(0.2)
        backend = DeadlineBackend(
            delay=0.3,
            replies=[action("print('should not run')"), "Answer: 1"],
            stop_text=cfg.stop_text,
        )
        tmp = tempfile.mkdtemp(prefix="nlp-test-")
        result = run_episode(
            task_id=TASK, condition="A", cfg=cfg, backend=backend, runs_root=tmp, split="DEV"
        )
        ep = result["episode"]
        self.assertEqual(ep["termination_reason"], "task_timeout")
        self.assertEqual(ep["status"], "timeout")
        self.assertIsNone(ep["final_answer"])
        self.assertEqual(ep["model_calls"], 1, "时间耗尽后不得再请求最终轮")
        self.assertEqual(ep["tool_attempts_executed"], 0, "被截止的轮次不执行动作")

        lines = Path(result["turns_path"]).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        turn = json.loads(lines[0])
        self.assertTrue(turn["cut_by_deadline"])
        self.assertEqual(turn["finish_reason"], "deadline")
        self.assertIsNone(turn["action"])
        self.assertEqual(
            turn["feedback_metadata"]["note"], "generation_cut_by_task_timeout"
        )

        ep_json = json.loads(Path(result["episode_path"]).read_text(encoding="utf-8"))
        self.assertEqual(ep_json["task_seconds_limit"], 0.2)
        self.assertGreaterEqual(ep_json["generation_stopped_task_seconds"], 0.2)
        self.assertGreaterEqual(
            ep_json["episode_written_task_seconds"],
            ep_json["generation_stopped_task_seconds"],
        )
        self.assertGreaterEqual(ep_json["post_generation_seconds"], 0.0)
        self.assertLess(ep_json["post_generation_seconds"], 1.0, "落盘开销应是毫秒级")
        self.assertTrue(ep_json["deadline_exceeded"])
        self.assertIsNotNone(ep_json["generation_stopped_at"])
        self.assertIsNotNone(ep_json["episode_written_at"])

    def test_timing_fields_present_on_normal_episode(self) -> None:
        result, _root, _backend = self.run_episode([action("print(1)"), "Answer: 7"])
        ep = json.loads(Path(result["episode_path"]).read_text(encoding="utf-8"))
        for key in (
            "task_started_at",
            "task_deadline_at",
            "task_seconds_limit",
            "generation_stopped_at",
            "generation_stopped_task_seconds",
            "last_generation_finish_reason",
            "episode_written_at",
            "episode_written_task_seconds",
            "post_generation_seconds",
            "deadline_overrun_seconds",
            "deadline_exceeded",
        ):
            self.assertIn(key, ep)
        self.assertFalse(ep["deadline_exceeded"])
        self.assertEqual(ep["deadline_overrun_seconds"], 0)
        self.assertLessEqual(ep["generation_stopped_at"], ep["episode_written_at"])
        self.assertGreaterEqual(
            ep["episode_written_task_seconds"], ep["generation_stopped_task_seconds"]
        )

        turn = json.loads(
            Path(result["turns_path"]).read_text(encoding="utf-8").splitlines()[0]
        )
        self.assertIn("generation_seconds", turn)
        self.assertFalse(turn["cut_by_deadline"])
        self.assertEqual(turn["finish_reason"], "stop")

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
        self.assertEqual(first["events"][-1]["execution_status"], "blocked")

    def test_task_level_limit_32(self) -> None:
        """32 次尝试用尽后进最终轮；最终轮的回复若是 Action 也不执行（禁工具）。

        修复前：第 9 个交互轮照常发起，第 33 次调用被拦（blocked=1）。
        修复后：预算用尽即进最终轮，最终轮回复的 Action 不产生任何工具事件。
        """
        code = "find_flights('E', 'A', '2023-12-25')\n" * 4
        replies = [action(code)] * 8 + [action("find_flights('E', 'A', '2023-12-25')"), "Answer: ok"]
        result, _root, backend = self.run_episode(replies)
        ep = result["episode"]
        self.assertEqual(ep["tool_attempts_executed"], 32)
        self.assertEqual(ep["tool_attempts_blocked"], 0)
        self.assertEqual(ep["termination_reason"], "no_answer_after_tool_budget_exhausted")
        self.assertIsNone(ep["final_answer"])
        self.assertEqual(backend.calls, 9)

    # ---------- 工具预算耗尽 → 立即进最终轮（课程附件 §2 转换要求） ----------
    def test_tool_budget_exhaustion_moves_next_call_to_final_turn(self) -> None:
        """32 次尝试用尽后，下一次模型调用必须是 final-only 轮。

        C 验收（docs/C_DEV_V4_REVIEW_20261125.md）判 v4 FAIL 的正是这一点：
        旧实现在预算用尽后继续留在交互轮拦截调用，直到轮次耗尽。
        """
        code = "find_flights('E', 'A', '2023-12-25')\n" * 4
        # 8 块 × 4 次 = 32 次尝试；第 9 个回复给最终轮；第 10 个回复永远不应被消费
        replies = [action(code)] * 8 + ["Answer: ok", action("print('forbidden')")]
        result, _root, backend = self.run_episode(replies)
        ep = result["episode"]
        self.assertEqual(ep["termination_reason"], "final_answer_after_tool_budget_exhausted")
        self.assertEqual(ep["final_answer"], "ok")
        self.assertEqual(ep["model_calls"], 9, "预算用尽后不得再发起交互轮")
        self.assertEqual(backend.calls, 9, "第 10 个回复（交互 Action）不应被消费")
        self.assertEqual(ep["tool_attempts_executed"], 32)
        self.assertEqual(ep["tool_attempts_blocked"], 0)

        turns = [json.loads(x) for x in Path(result["turns_path"]).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(turns), 9)
        final_flags = [t["generation_settings"]["is_final_turn"] for t in turns]
        self.assertEqual(final_flags, [False] * 8 + [True], "只有最后一轮是 final-only")
        self.assertEqual(turns[-1]["generation_settings"]["max_new_tokens"], 128)
        self.assertEqual(turns[-1]["events"], [])
        # 前 8 个交互轮每轮恰好 4 次执行，且没有任何一轮在预算用尽后出现
        cumulative = 0
        for t in turns[:-1]:
            cumulative += len(t["events"])
        self.assertEqual(cumulative, 32)

    def test_blocked_attempts_consume_task_budget(self) -> None:
        """blocked 也消耗任务尝试预算（C 审计口径：attempts = executed + blocked）。

        第 8 块第 5 次调用被拦（attempt 33），blocked 计入预算后同样触发
        “下一次调用进最终轮”。
        """
        full = "find_flights('E', 'A', '2023-12-25')\n" * 4
        overrun = "find_flights('E', 'A', '2023-12-25')\n" * 5 + "print('done')"
        replies = [action(full)] * 7 + [action(overrun), "Answer: ok"]
        result, _root, backend = self.run_episode(replies)
        ep = result["episode"]
        self.assertEqual(ep["tool_attempts_executed"], 32)
        self.assertEqual(ep["tool_attempts_blocked"], 1)
        self.assertEqual(ep["termination_reason"], "final_answer_after_tool_budget_exhausted")
        self.assertEqual(ep["final_answer"], "ok")
        self.assertEqual(backend.calls, 9, "blocked 计入预算后不得再发起交互轮")

    def test_deadline_priority_over_tool_budget_transition(self) -> None:
        """硬时间截止优先：工具预算刚用尽、执行又跨过任务截止时，不再请求最终轮模型。"""
        import dataclasses as _dc

        # 生成耗时极小（0.001s，Windows 粒度下 7 次也远小于 0.3s）；
        # 前 7 块只调工具（不 sleep），第 8 块执行里 sleep(1)：在 Linux 上被
        # 剩余时间钳制（SIGALRM 真中断），在 Windows 上（alarm 退化）自然跑满
        # 任务 0.3s——两条路径都收敛到 termination=task_timeout，且不再请求最终轮。
        raw = {**self.cfg.raw, "limits": {**self.cfg.raw["limits"], "task_seconds": 0.3}}
        cfg = _dc.replace(self.cfg, raw=raw)
        tool_block = "find_flights('E', 'A', '2023-12-25')\n" * 4
        slow = DeadlineBackend(
            delay=0.001,
            replies=[action(tool_block)] * 7
            + [action(tool_block + "import time\ntime.sleep(1)")],
            stop_text=cfg.stop_text,
        )
        tmp = tempfile.mkdtemp(prefix="nlp-test-")
        result = run_episode(
            task_id=TASK, condition="A", cfg=cfg, backend=slow, runs_root=tmp, split="DEV"
        )
        ep = result["episode"]
        self.assertEqual(ep["termination_reason"], "task_timeout", "硬截止优先于工具预算转换")
        self.assertEqual(ep["status"], "timeout")
        self.assertIsNone(ep["final_answer"])
        self.assertEqual(ep["model_calls"], 8, "时间耗尽后不得请求最终轮")
        self.assertEqual(ep["tool_attempts_executed"], 32)

    def test_prior_effects_retained_across_final_turn_transition(self) -> None:
        """预算用尽前的执行效果保留：交互轮照常运行，直到尝试数真正到顶。"""
        code = "total = 6\nfind_flights('E', 'A', '2023-12-25')\n" * 4  # 每块 4 次
        replies = (
            [action(code)] * 7               # 28 次尝试
            + [action("print(total)")]       # 第 8 轮：28 < 32，交互轮照常
            + [action(code)]                 # 第 9 轮：到 32 次用尽
            + ["Answer: ok"]                 # 最终轮
        )
        result, _root, backend = self.run_episode(replies)
        ep = result["episode"]
        self.assertEqual(ep["tool_attempts_executed"], 32)
        self.assertEqual(ep["termination_reason"], "final_answer_after_tool_budget_exhausted")
        self.assertEqual(ep["final_answer"], "ok")
        self.assertEqual(backend.calls, 10)  # 9 交互 + 1 最终轮
        turns = [json.loads(x) for x in Path(result["turns_path"]).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(turns), 10)
        self.assertFalse(turns[7]["generation_settings"]["is_final_turn"])
        self.assertIn("6", turns[7]["python_output"], "第 1 块的赋值效果在第 8 轮仍可见")

    # ---------- 状态隔离 ----------
    def test_variables_reset_between_tasks(self) -> None:
        result1, _r1, _b1 = self.run_episode([action("secret = 123\nprint(secret)"), "Answer: 1"])
        self.assertEqual(result1["episode"]["status"], "completed")

        result2, root2, _b2 = self.run_episode([action("print(secret)"), "Answer: 2"])
        turns = Path(result2["turns_path"])
        first = json.loads(turns.read_text(encoding="utf-8").splitlines()[0])
        self.assertIn("NameError", first["python_output"])
        self.assertEqual(result2["episode"]["status"], "completed")

    # ---------- 记录契约：必须被 C 的审计读取器直接接受 ----------
    def test_record_matches_audit_contract(self) -> None:
        from src.evaluation.turns_reader import read_turns

        result, _root, _backend = self.run_episode([action("print(1)"), "Answer: 3"])
        turns = read_turns(result["turns_path"])  # 缺字段/类型错会抛 InputError
        self.assertEqual([t["turn_index"] for t in turns], list(range(1, len(turns) + 1)))
        produced = [t for t in turns if t["produced_final_answer"]]
        self.assertEqual(len(produced), 1)
        self.assertFalse(produced[0]["is_final_answer_turn"])  # 交互轮答出，仍受 384
        ep = result["episode"]
        self.assertRegex(str(ep.get("code_commit")), r"^[0-9a-f]{40}$")
        self.assertEqual(ep.get("model_revision"), self.cfg.model["revision"])

    def test_final_only_turn_is_flagged(self) -> None:
        from src.evaluation.turns_reader import read_turns

        replies = [action("print(1)") for _ in range(12)] + ["Answer: 7"]
        result, _root, _backend = self.run_episode(replies)
        turns = read_turns(result["turns_path"])
        self.assertTrue(turns[-1]["is_final_answer_turn"])
        self.assertTrue(turns[-1]["produced_final_answer"])
        self.assertEqual([i for i, t in enumerate(turns) if t["is_final_answer_turn"]], [len(turns) - 1])
        self.assertEqual(result["episode"]["final_answer"], "7")

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


class BudgetLimitTest(unittest.TestCase):
    """预算上限的边界：上下文、每轮 384、总 3072 里预留最终轮 128。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.limits = load_course_config().limits

    def test_context_cap_zeroes_generation(self) -> None:
        from src.runtime.budget import Budget

        budget = Budget(self.limits)
        alloc = budget.allocate(prompt_tokens=self.limits.context_tokens + 1)
        self.assertEqual(alloc.remaining_context, 0)
        self.assertEqual(alloc.max_new_tokens, 0)

    def test_turn_cap_is_384_and_reserve_is_128(self) -> None:
        from src.runtime.budget import Budget

        budget = Budget(self.limits)
        self.assertEqual(
            budget.allocate(prompt_tokens=10).max_new_tokens,
            self.limits.tokens_per_interaction,
        )
        budget.charge(
            completion_tokens=self.limits.total_generated_tokens
            - self.limits.final_answer_tokens
        )
        # 交互轮分不到预算（只剩预留给最终轮的 128），最终轮仍能拿到 128
        self.assertEqual(budget.allocate(prompt_tokens=10).max_new_tokens, 0)
        self.assertEqual(
            budget.allocate(prompt_tokens=10, is_final=True).max_new_tokens,
            self.limits.final_answer_tokens,
        )


class PromptSignatureTest(unittest.TestCase):
    """课程附件 §3：提示里的工具签名必须与真实函数一致（PR #3 审查发现项）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cfg = load_course_config()

    def test_find_flights_signature_fixed(self) -> None:
        task = get_task("travel_itinerary_planning/cheapest_new_york_trip")
        prompt = build_system_prompt(task, self.cfg)
        self.assertIn(
            "find_flights(from_location: str, to_location: str, date: str)", prompt
        )
        self.assertNotIn("find_flights(destination", prompt)

    def test_message_decoder_s_params_fixed(self) -> None:
        task = get_task("message_decoder/specific_decoded_character")
        prompt = build_system_prompt(task, self.cfg)
        self.assertIn("reverse_string(s: str)", prompt)
        self.assertIn("string_length(s: str)", prompt)
        self.assertNotIn("reverse_string(string", prompt)
        self.assertNotIn("string_length(string", prompt)


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
