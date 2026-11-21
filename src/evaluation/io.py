"""Input readers for C's offline tools.

Rules enforced here:
  * explicit errors on missing/duplicate/unknown reference entries;
  * episode inputs can be a single JSON, a JSONL index, or a directory;
  * synthetic data is refused unless explicitly allowed;
  * no silent defaults for malformed records.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import DataError, InputError, SyntheticNotAllowed
from .scoring import SUPPORTED_ANSWER_TYPES

_EPISODE_MARKERS = ("task_id", "condition", "final_answer", "status")


@dataclass
class ReferenceSet:
    index: dict[str, dict[str, Any]]
    synthetic: bool
    source: str


def read_json(path: str | Path) -> Any:
    p = Path(path)
    if not p.is_file():
        raise InputError(f"file not found: {p}")
    try:
        with p.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid JSON in {p}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise InputError(f"invalid UTF-8 in {p}: {exc}") from exc


def read_jsonl(path: str | Path) -> list[dict]:
    """Read a JSONL file; every non-blank line must be a JSON object."""
    p = Path(path)
    if not p.is_file():
        raise InputError(f"file not found: {p}")
    records: list[dict] = []
    try:
        with p.open("r", encoding="utf-8") as handle:
            for line_no, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                try:
                    value = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise InputError(f"invalid JSONL at {p}:{line_no}: {exc}") from exc
                if not isinstance(value, dict):
                    raise InputError(
                        f"JSONL line {p}:{line_no} must be an object, got {type(value).__name__}"
                    )
                records.append(value)
    except UnicodeDecodeError as exc:
        raise InputError(f"invalid UTF-8 in {p}: {exc}") from exc
    return records


def write_jsonl(path: str | Path, records: list[dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: str | Path, value: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")


def _looks_like_episode(value: Any) -> bool:
    return isinstance(value, dict) and any(key in value for key in _EPISODE_MARKERS)


def load_episodes(path: str | Path) -> tuple[list[dict], list[str]]:
    """Return (episodes, source_paths) from a JSON episode, JSONL index or directory.

    A JSONL index uses one of two line forms:
      {"episode_path": "relative/path/episode.json"}   # resolved by index dir
      { ... episode object inline ... }
    Directory mode records the exact sorted file list it consumed so stale
    runs can never be silently mixed in.
    """
    p = Path(path)
    sources: list[str] = []
    episodes: list[dict] = []

    if p.is_dir():
        files = sorted(q for q in p.rglob("*.json") if q.is_file())
        candidates = [q for q in files if _looks_like_episode(read_json(q))]
        for q in candidates:
            value = read_json(q)
            if isinstance(value, list):
                for idx, item in enumerate(value):
                    if not _looks_like_episode(item):
                        raise InputError(f"{q}[{idx}] is not an episode object")
                    episodes.append(item)
                    sources.append(f"{q}#{idx}")
            else:
                episodes.append(value)
                sources.append(str(q))
        if not episodes:
            raise InputError(f"no episode JSON files found under directory {p}")
        return episodes, sources

    if not p.is_file():
        raise InputError(f"episodes path not found: {p}")

    if p.suffix == ".jsonl":
        for line_no, item in enumerate(read_jsonl(p), 1):
            if "episode_path" in item:
                ref_path = Path(str(item["episode_path"]))
                if not ref_path.is_absolute():
                    ref_path = p.parent / ref_path
                value = read_json(ref_path)
                if not isinstance(value, dict):
                    raise InputError(f"{ref_path} referenced at {p}:{line_no} is not an object")
                episodes.append(value)
                sources.append(str(ref_path))
            elif _looks_like_episode(item):
                episodes.append(item)
                sources.append(f"{p}:{line_no}")
            else:
                raise InputError(
                    f"{p}:{line_no} has neither 'episode_path' nor episode fields"
                )
        if not episodes:
            raise InputError(f"episode index {p} is empty")
        return episodes, sources

    if p.suffix == ".json":
        value = read_json(p)
        if isinstance(value, list):
            for idx, item in enumerate(value):
                if not _looks_like_episode(item):
                    raise InputError(f"{p}[{idx}] is not an episode object")
                episodes.append(item)
                sources.append(f"{p}#{idx}")
        elif isinstance(value, dict) and isinstance(value.get("episodes"), list):
            for idx, item in enumerate(value["episodes"]):
                if not _looks_like_episode(item):
                    raise InputError(f"{p}['episodes'][{idx}] is not an episode object")
                episodes.append(item)
                sources.append(f"{p}#episodes[{idx}]")
        elif _looks_like_episode(value):
            episodes.append(value)
            sources.append(str(p))
        else:
            raise InputError(f"{p} does not contain any recognizable episode")
        return episodes, sources

    raise InputError(f"unsupported episodes path suffix: {p.suffix}")


def load_reference_index(path: str | Path) -> ReferenceSet:
    """Load and validate the offline reference file (answer types from data)."""
    p = Path(path)
    value = read_json(p)
    if isinstance(value, list):
        entries = value
        synthetic = False
    elif isinstance(value, dict):
        entries = value.get("references")
        synthetic = bool(value.get("synthetic", False))
        if not isinstance(entries, list):
            raise DataError(f"reference file {p} has no 'references' list")
    else:
        raise DataError(f"reference file {p} must be an object or list")

    index: dict[str, dict[str, Any]] = {}
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise DataError(f"reference entry {p}[{i}] must be an object")
        task_id = entry.get("task_id")
        answer_type = entry.get("answer_type")
        if not isinstance(task_id, str) or not task_id:
            raise DataError(f"reference entry {p}[{i}] has invalid task_id: {task_id!r}")
        if answer_type not in SUPPORTED_ANSWER_TYPES:
            raise DataError(
                f"reference entry for {task_id!r} has unknown answer_type {answer_type!r}"
            )
        if "reference" not in entry:
            raise DataError(f"reference entry for {task_id!r} is missing 'reference'")
        if task_id in index:
            raise DataError(f"duplicate reference for task_id={task_id!r} in {p}")
        index[task_id] = entry
    if not index:
        raise DataError(f"reference file {p} contains no references")
    return ReferenceSet(index=index, synthetic=synthetic, source=str(p))


def is_synthetic_record(record: dict) -> bool:
    """A record is synthetic if it self-declares synthetic or uses the synthetic split."""
    return bool(record.get("synthetic", False)) or str(record.get("split", "")).upper() == "SYNTHETIC"


def assert_synthetic_allowed(records: list[dict], allow_synthetic: bool, *, context: str) -> bool:
    """Reject synthetic input unless explicitly allowed; return whether any was synthetic."""
    found = [i for i, record in enumerate(records) if is_synthetic_record(record)]
    if found and not allow_synthetic:
        raise SyntheticNotAllowed(
            f"{context} contains synthetic record(s) at index {found}; "
            "re-run with --allow-synthetic to use synthetic data"
        )
    return bool(found)


def resolve_synthetic_tasks(spec: str | None) -> list[str] | None:
    """Resolve an explicit synthetic task list (file path or comma-separated ids)."""
    if not spec:
        return None
    p = Path(spec)
    if p.is_file():
        value = read_json(p)
        if isinstance(value, dict):
            value = value.get("tasks") or value.get("synthetic_tasks")
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise InputError(f"synthetic task spec {p} must be a JSON list of task ids")
        tasks = value
    else:
        tasks = [item.strip() for item in spec.split(",") if item.strip()]
    if not tasks:
        raise InputError("synthetic task list is empty")
    if len(tasks) != len(set(tasks)):
        raise InputError("synthetic task list contains duplicates")
    return tasks
