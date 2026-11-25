"""运行统计脚本的验收测试（只读 episode.json，不碰 GPU）。

守两件事：
- 计数与中位数按条件分开，无答案不被当成 0 分混进“有答案”；
- `pilot_*` 留档目录不参与统计（否则 16 题会被算成 17 条）。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_stats import load_episodes, summarize  # noqa: E402


def write_episode(root: Path, task: str, cond: str, *, answer: str | None, wall: float,
                  executed: int = 1, blocked: int = 0) -> None:
    d = root / "DEV" / cond / f"{task.replace('/', '_')}_x"
    d.mkdir(parents=True, exist_ok=True)
    (d / "episode.json").write_text(
        json.dumps(
            {
                "task_id": task,
                "split": "DEV",
                "condition": cond,
                "status": "completed",
                "termination_reason": "answer" if answer else "token_budget_exhausted",
                "final_answer": answer,
                "input_tokens": 100,
                "output_tokens": 10,
                "model_calls": 2,
                "tool_attempts_executed": executed,
                "tool_attempts_blocked": blocked,
                "wall_seconds": wall,
            }
        ),
        encoding="utf-8",
    )


class SummaryTest(unittest.TestCase):
    def test_counts_and_medians(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_episode(root, "a/one", "A", answer="1", wall=10.0)
            write_episode(root, "a/two", "A", answer=None, wall=30.0, executed=0, blocked=2)
            write_episode(root, "a/one", "B", answer="1", wall=20.0)
            episodes, skipped = load_episodes(root, "DEV")
            self.assertEqual(skipped, 0)
            text = summarize(episodes)
            self.assertIn("| A | 2 | 1 | 1 |", text)
            self.assertIn("| B | 1 | 1 | 0 |", text)
            self.assertIn("20.0s", text)  # A 的中位耗时 = (10+30)/2
            self.assertIn("token_budget_exhausted", text)

    def test_pilot_dir_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_episode(root, "a/one", "A", answer="1", wall=10.0)
            pilot = root / "DEV" / "A" / "pilot_123"
            pilot.mkdir(parents=True)
            (pilot / "episode.json").write_text(
                json.dumps({"task_id": "a/one", "split": "DEV", "condition": "A",
                            "status": "timeout", "final_answer": None, "wall_seconds": 180}),
                encoding="utf-8",
            )
            episodes, skipped = load_episodes(root, "DEV")
            self.assertEqual(len(episodes), 1)
            self.assertEqual(skipped, 1)


if __name__ == "__main__":
    unittest.main()
