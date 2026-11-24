"""答案隔离的回归测试。

两层证据：
1. 模型看到的 system prompt（43 个任务全部渲染一遍）里没有上游 `print_task()` 的答案标记；
2. 记录扫描脚本能识别泄漏：正例必须被抓到，干净目录必须 PASS。

注意：单字符答案（如 `4`）会与任务描述里的价格数字重合，因此**不能**用“答案值子串是否出现”
来自动判定泄漏；真正要证的是“harness 没有把答案追加进去”，用标记与字段名来判。
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

from scripts.check_answer_isolation import iter_episode_files, scan  # noqa: E402
from src.runtime.config import load_course_config  # noqa: E402
from src.runtime.runner import build_system_prompt  # noqa: E402
from src.runtime.tasks import get_task  # noqa: E402


class PromptIsolationTest(unittest.TestCase):
    def test_no_answer_marker_in_any_prompt(self) -> None:
        cfg = load_course_config()
        for task_id in cfg.task_ids("DEV") + cfg.task_ids("EVAL"):
            with self.subTest(task_id=task_id):
                prompt = build_system_prompt(get_task(task_id), cfg)
                self.assertNotIn("Expected Output:", prompt)
                self.assertNotIn("expected_output", prompt)
                self.assertNotIn("is_correct", prompt)

    def test_prompt_is_task_prompt_plus_contract(self) -> None:
        cfg = load_course_config()
        task = get_task("travel_itinerary_planning/cheapest_new_york_trip")
        prompt = build_system_prompt(task, cfg)
        self.assertTrue(prompt.startswith("You have access to the following tools:"))
        self.assertTrue(prompt.endswith(cfg.initial_contract))


class RecordScannerTest(unittest.TestCase):
    def _make_run(self, root: Path, content: str) -> None:
        ep = root / "runs" / "X" / "task_a"
        ep.mkdir(parents=True)
        (ep / "episode.json").write_text(
            json.dumps({"task_id": "x/y", "status": "completed", "final_answer": "1"}),
            encoding="utf-8",
        )
        (ep / "turns.jsonl").write_text(content + "\n", encoding="utf-8")

    def test_clean_record_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_run(root, json.dumps({"turn_index": 0, "python_output": "ok"}))
            files = iter_episode_files(root / "runs")
            self.assertEqual(len(files), 2)
            self.assertEqual(scan(files), [])

    def test_leaked_marker_is_caught(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_run(root, json.dumps({"turn_index": 0, "python_output": "Expected Output: 42"}))
            hits = scan(iter_episode_files(root / "runs"))
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0][2], "Expected Output:")

    def test_reference_field_is_caught(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_run(root, json.dumps({"reference_answer": "42"}))
            hits = scan(iter_episode_files(root / "runs"))
            self.assertEqual([h[2] for h in hits], ["reference_answer"])


if __name__ == "__main__":
    unittest.main()
