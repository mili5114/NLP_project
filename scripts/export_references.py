"""导出固定上游版本的离线参考答案。

课程附件 §2：参考答案只能用于离线评分，不得进入模型输入、模型可见反馈或代码执行环境。
因此本脚本：

* 只写一个离线 JSON，不把答案写进 `runs/`、`src/`、`configs/course/`；
* stdout 只输出计数与 hash，不打印任何答案值；
* 写完后用 C 的 `src/evaluation/io.load_reference_index()` 重新读一遍，
  证明评分器可以直接消费这份文件（格式不接受就直接失败，不静默降级）。

用法：

    python scripts/export_references.py                      # 写 references/offline_reference_v1.json
    python scripts/export_references.py --out <path> --force

`answer_type` 取自固定上游任务对象的 `expected_output` 真实类型（int/float → numeric，str → string），
不靠任务名或预测内容猜测；遇到无法判定的类型直接报错。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.runtime.config import load_course_config, repo_root, sha256_file  # noqa: E402
from src.runtime.tasks import load_tasks, module_of  # noqa: E402

SCHEMA_VERSION = "1"
DEFAULT_OUT = "references/offline_reference_v1.json"
FORBIDDEN_PREFIXES = ("runs", "src", "configs/course", "third_party")


class ExportError(RuntimeError):
    """导出前置条件不满足（缺任务、类型不明、路径越界）。"""


def answer_type_of(value: Any) -> str:
    """把参考答案的 Python 类型映射到评分器的 answer_type，不猜测。"""
    if isinstance(value, bool):
        raise ExportError("参考答案不能是 bool，无法映射到 numeric/string")
    if isinstance(value, int):
        return "numeric"
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ExportError("参考答案是 NaN/Inf，无法做 Decimal 比较")
        return "numeric"
    if isinstance(value, str):
        return "string"
    raise ExportError(f"参考答案类型 {type(value).__name__} 不在 numeric/string 之内")


def reference_text(value: Any, answer_type: str) -> str:
    """numeric 用可精确解析的十进制文本，string 原样保留（评分端负责 strip）。"""
    if answer_type == "numeric":
        if isinstance(value, int):
            return str(value)
        text = repr(float(value))
        if "e" in text or "E" in text:  # 极小/极大值改写成普通十进制，方便人工核对
            from decimal import Decimal

            return format(Decimal(text), "f")
        return text
    return value


def _check_out_path(out: Path) -> None:
    rel = out.resolve().relative_to(REPO_ROOT.resolve())
    posix = rel.as_posix()
    for prefix in FORBIDDEN_PREFIXES:
        if posix == prefix or posix.startswith(prefix + "/"):
            raise ExportError(
                f"参考答案不能写到 {posix!r}：只允许离线文件，且不得进入运行记录/执行环境"
            )


def collect(splits: Iterable[str]) -> list[dict[str, Any]]:
    """按课程 split_manifest 顺序收集参考条目；每个 task_id 必须唯一且能加载。"""
    cfg = load_course_config()
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    module_cache: dict[str, dict[str, Any]] = {}

    for split in splits:
        if split not in cfg.split:
            raise ExportError(f"split {split!r} 不在 split_manifest.json 里")
        for task_id in cfg.task_ids(split):
            if task_id in seen:
                raise ExportError(f"task_id {task_id!r} 在 split 清单里重复")
            module_name = module_of(task_id)
            if module_name not in module_cache:
                module_cache[module_name] = load_tasks(module_name)
            task = module_cache[module_name].get(task_id)
            if task is None:
                raise ExportError(f"{task_id!r} 在模块 {module_name} 里找不到")
            answer_type = answer_type_of(task.expected_output)
            entries.append(
                {
                    "task_id": task_id,
                    "split": split,
                    "answer_type": answer_type,
                    "reference": reference_text(task.expected_output, answer_type),
                }
            )
            seen.add(task_id)
    return entries


def build_payload(entries: list[dict[str, Any]]) -> dict[str, Any]:
    cfg = load_course_config()
    versions_path = repo_root() / "configs" / "versions.json"
    versions = json.loads(versions_path.read_text(encoding="utf-8"))
    canonical = json.dumps(entries, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["split"]] = counts.get(entry["split"], 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "synthetic": False,
        "offline_only": True,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "scripts/export_references.py",
        "upstream_code_commit": versions["upstream_code_commit"],
        "model_revision": versions["model"]["revision"],
        "split_manifest_sha256": sha256_file(repo_root() / "configs" / "course" / "split_manifest.json"),
        "counts": counts,
        "content_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "references": entries,
    }


def build_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    """可公开提交的清单：只含 task_id / answer_type / 每条的 sha256，不含答案原文。

    仓库是公开的，答案原文不进 git；C 用同一脚本本地生成后按 hash 交叉校验。
    """
    return {
        "schema_version": payload["schema_version"],
        "synthetic": False,
        "offline_only": True,
        "generated_at": payload["generated_at"],
        "generated_by": payload["generated_by"],
        "upstream_code_commit": payload["upstream_code_commit"],
        "model_revision": payload["model_revision"],
        "split_manifest_sha256": payload["split_manifest_sha256"],
        "counts": payload["counts"],
        "content_sha256": payload["content_sha256"],
        "answers_in_git": False,
        "reproduce": "python scripts/export_references.py --out <path>",
        "entries": [
            {
                "task_id": entry["task_id"],
                "split": entry["split"],
                "answer_type": entry["answer_type"],
                "reference_sha256": hashlib.sha256(
                    str(entry["reference"]).encode("utf-8")
                ).hexdigest(),
            }
            for entry in payload["references"]
        ],
    }


def verify(path: Path) -> int:
    """用评分器自己的读取器复核：格式不被接受就直接失败。"""
    from src.evaluation.io import load_reference_index

    refset = load_reference_index(path)
    if refset.synthetic:
        raise ExportError("导出的文件被判定为 synthetic，不能用于正式评分")
    return len(refset.index)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导出固定上游版本的离线参考答案")
    parser.add_argument("--out", default=DEFAULT_OUT, help=f"输出路径（默认 {DEFAULT_OUT}）")
    parser.add_argument(
        "--splits", nargs="+", default=["DEV", "EVAL"], help="要导出的 split（默认 DEV EVAL）"
    )
    parser.add_argument("--force", action="store_true", help="允许覆盖已存在的输出文件")
    parser.add_argument(
        "--no-manifest", action="store_true", help="不写可提交的 hash 清单（默认会写）"
    )
    args = parser.parse_args(argv)

    out = Path(args.out)
    if not out.is_absolute():
        out = REPO_ROOT / out
    _check_out_path(out)
    if out.exists() and not args.force:
        raise ExportError(f"{out} 已存在；确认要覆盖时加 --force（避免无意改动已交接的文件）")

    entries = collect(args.splits)
    payload = build_payload(entries)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    loaded = verify(out)
    if loaded != len(entries):
        raise ExportError(f"复核条数不一致：写入 {len(entries)}，评分器读到 {loaded}")

    manifest_path = out.with_name(out.stem + ".manifest.json")
    if not args.no_manifest:
        manifest = build_manifest(payload)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    print(f"wrote {out.relative_to(REPO_ROOT)}（答案原文，不进 git）")
    if not args.no_manifest:
        print(f"wrote {manifest_path.relative_to(REPO_ROOT)}（可提交的 hash 清单）")
    print(f"entries={len(entries)} counts={payload['counts']}")
    print(f"content_sha256={payload['content_sha256']}")
    print(f"file_sha256={sha256_file(out)}")
    print(f"scorer_readback={loaded} ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
