"""课程配置的唯一读取入口。

模块里不许再写一份预算数字或任务名单：所有限制都来自 configs/course/。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Limits:
    interaction_turns: int
    tokens_per_interaction: int
    final_answer_tokens: int
    total_generated_tokens: int
    context_tokens: int
    tool_attempts_per_action: int
    tool_attempts_per_task: int
    task_seconds: float
    action_seconds: float
    feedback_characters: int


@dataclass(frozen=True)
class CourseConfig:
    root: Path
    raw: dict[str, Any]
    split: dict[str, list[str]]
    hashes: dict[str, str]

    # ---- 便捷访问 ----
    @property
    def limits(self) -> Limits:
        lim = self.raw["limits"]
        return Limits(
            interaction_turns=int(lim["interaction_turns"]),
            tokens_per_interaction=int(lim["tokens_per_interaction"]),
            final_answer_tokens=int(lim["final_answer_tokens"]),
            total_generated_tokens=int(lim["total_generated_tokens"]),
            context_tokens=int(lim["context_tokens"]),
            tool_attempts_per_action=int(lim["tool_attempts_per_action"]),
            tool_attempts_per_task=int(lim["tool_attempts_per_task"]),
            task_seconds=float(lim["task_seconds"]),
            action_seconds=float(lim["action_seconds"]),
            feedback_characters=int(lim["feedback_characters"]),
        )

    @property
    def stop_text(self) -> str:
        return self.raw["stop_text"]

    @property
    def truncation_marker(self) -> str:
        return self.raw["truncation_marker"]

    @property
    def initial_contract(self) -> str:
        return self.raw["initial_contract"]

    @property
    def final_answer_request(self) -> str:
        return self.raw["final_answer_request"]

    @property
    def full_trace_format(self) -> dict[str, str]:
        return self.raw["full_trace_format"]

    @property
    def model(self) -> dict[str, Any]:
        return self.raw["model"]

    @property
    def backend_options(self) -> dict[str, Any]:
        return self.raw["backend_options"]

    @property
    def code_commit(self) -> str:
        return self.raw["code_commit"]

    def task_ids(self, split: str) -> list[str]:
        return list(self.split[split])

    def load_class_name(self) -> str:
        return self.backend_options["transformers"]["class"]


def _load_declared_hashes(path: Path) -> dict[str, str]:
    """source_hashes.json 是 [{file, Hash}] 列表（教师给的原始格式），统一成小写 dict。"""
    if not path.exists():
        return {}
    data = _read_json(path)
    if isinstance(data, dict):
        return {k: str(v).lower() for k, v in data.items()}
    return {item["file"]: str(item["Hash"]).lower() for item in data}


def load_course_config(root: Path | None = None) -> CourseConfig:
    base = (root or repo_root()) / "configs" / "course"
    settings_path = base / "runtime_settings.json"
    split_path = base / "split_manifest.json"
    hashes_path = base / "source_hashes.json"

    raw = _read_json(settings_path)
    split = _read_json(split_path)

    declared = _load_declared_hashes(hashes_path)
    actual: dict[str, str] = {}
    for name in declared:
        candidate = base / name
        if candidate.exists():
            actual[name] = sha256_file(candidate)
    mismatched = {k: {"declared": declared[k], "actual": actual.get(k)} for k in declared if actual.get(k) != declared[k]}

    return CourseConfig(
        root=base.parents[1],
        raw=raw,
        split=split,
        hashes={**actual, "_declared": declared, "_mismatched": mismatched},
    )


def safe_slug(text: str) -> str:
    """把 task_id / run_id 变成可做文件名的 slug，原始 id 仍写进记录字段。"""
    out = []
    for ch in text:
        if ch.isalnum() or ch in ("-", "_"):
            out.append(ch)
        else:
            out.append("_")
    slug = "".join(out).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug[:120] or "unnamed"
