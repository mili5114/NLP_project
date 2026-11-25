"""离线参考答案导出的验收测试（CPU，不需要 GPU）。

关心三件事：
- answer_type 来自真实 `expected_output` 类型，不猜；无法判定的类型必须报错；
- 导出覆盖 split_manifest 里的全部任务且每条唯一；
- 参考答案只能写进离线文件，不能写进 runs/、src/、configs/course/。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.export_references import (  # noqa: E402
    ExportError,
    _check_out_path,
    answer_type_of,
    collect,
    reference_text,
)


class AnswerTypeTest(unittest.TestCase):
    def test_numeric_types(self) -> None:
        self.assertEqual(answer_type_of(987), "numeric")
        self.assertEqual(answer_type_of(8100.0), "numeric")

    def test_string_type(self) -> None:
        self.assertEqual(answer_type_of("rzhehgavxMuxP"), "string")

    def test_bool_is_rejected(self) -> None:
        # True 是 int 的子类，若放过去会被当成 numeric=1，属静默错误。
        with self.assertRaises(ExportError):
            answer_type_of(True)

    def test_unknown_type_is_rejected(self) -> None:
        with self.assertRaises(ExportError):
            answer_type_of(["a", "b"])
        with self.assertRaises(ExportError):
            answer_type_of(None)

    def test_non_finite_float_is_rejected(self) -> None:
        with self.assertRaises(ExportError):
            answer_type_of(float("nan"))


class ReferenceTextTest(unittest.TestCase):
    def test_int_kept_as_integer(self) -> None:
        self.assertEqual(reference_text(987, "numeric"), "987")

    def test_float_kept_decimal(self) -> None:
        self.assertEqual(reference_text(8100.0, "numeric"), "8100.0")

    def test_tiny_float_expanded_not_scientific(self) -> None:
        self.assertEqual(reference_text(1e-07, "numeric"), "0.0000001")

    def test_string_untouched(self) -> None:
        self.assertEqual(reference_text("  abc  ", "string"), "  abc  ")


class OutPathGuardTest(unittest.TestCase):
    def test_runs_dir_refused(self) -> None:
        with self.assertRaises(ExportError):
            _check_out_path(REPO_ROOT / "runs" / "dev_full_v3" / "ref.json")

    def test_src_dir_refused(self) -> None:
        with self.assertRaises(ExportError):
            _check_out_path(REPO_ROOT / "src" / "ref.json")

    def test_references_dir_allowed(self) -> None:
        _check_out_path(REPO_ROOT / "references" / "offline_reference_v1.json")


class CollectTest(unittest.TestCase):
    def test_covers_manifest_once(self) -> None:
        entries = collect(["DEV", "EVAL"])
        task_ids = [e["task_id"] for e in entries]
        self.assertEqual(len(task_ids), len(set(task_ids)))
        self.assertEqual(len(entries), 43)
        counts: dict[str, int] = {}
        for entry in entries:
            counts[entry["split"]] = counts.get(entry["split"], 0) + 1
        self.assertEqual(counts, {"DEV": 16, "EVAL": 27})
        self.assertTrue(all(e["answer_type"] in {"numeric", "string"} for e in entries))
        self.assertTrue(all(str(e["reference"]).strip() for e in entries))

    def test_unknown_split_rejected(self) -> None:
        with self.assertRaises(ExportError):
            collect(["TEST"])

    def test_task_order_follows_manifest(self) -> None:
        from src.runtime.config import load_course_config

        entries = collect(["DEV"])
        self.assertEqual(
            [e["task_id"] for e in entries], load_course_config().task_ids("DEV")
        )


class ManifestTest(unittest.TestCase):
    """仓库是公开的：可提交清单里不能出现答案原文，只能有 hash。"""

    def test_manifest_has_no_answer_values(self) -> None:
        from scripts.export_references import build_manifest, build_payload

        manifest = build_manifest(build_payload(collect(["DEV", "EVAL"])))
        self.assertFalse(manifest["answers_in_git"])
        self.assertTrue(manifest["content_sha256"])
        for entry in manifest["entries"]:
            self.assertNotIn("reference", entry)
            self.assertEqual(len(entry["reference_sha256"]), 64)
            self.assertIn(entry["answer_type"], {"numeric", "string"})
        self.assertEqual(len(manifest["entries"]), 43)


if __name__ == "__main__":
    unittest.main()
