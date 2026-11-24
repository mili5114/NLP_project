"""为一个批次生成显式索引，并核对"唯一槽位"是否齐全（A 侧，只读）。

为什么需要它：

* C 的 `scripts/score.py` 在**目录模式**下会把 `manifest.json` 也当成 episode
  （manifest 里同时有 `task_id` 和 `condition`，命中了 `_looks_like_episode` 的判定），
  2 集会被算成 4 条。用显式 JSONL 索引（只列 `episode.json`）可以避免。
* 交接要求"明确的本批索引，排除 pilot、旧诊断批次及重复运行"：索引只指向本批目录，
  同时把缺槽位/重复槽位直接报出来。

用法：

    python scripts/make_run_index.py runs/dev_full_v3 --split DEV
    python scripts/make_run_index.py runs/dev_fix_check_v2 --split DEV --conditions A B

产物：`<batch>/index.jsonl`，每行 `{"episode_path", "task_id", "split", "condition", "status"}`。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.runtime.config import load_course_config  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="生成批次索引并核对唯一槽位")
    ap.add_argument("batch", help="批次目录，例如 runs/dev_full_v3")
    ap.add_argument("--split", default="DEV")
    ap.add_argument("--conditions", nargs="+", default=["A", "B"])
    ap.add_argument("--out", help="默认 <batch>/index.jsonl")
    args = ap.parse_args(argv)

    batch = Path(args.batch)
    if not batch.is_absolute():
        batch = REPO_ROOT / batch
    if not batch.is_dir():
        print(f"ERROR: {batch} 不是目录", file=sys.stderr)
        return 2

    entries: list[dict] = []
    for path in sorted(batch.rglob("episode.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        entries.append(
            {
                "episode_path": str(path.relative_to(batch).as_posix()),
                "task_id": data.get("task_id"),
                "split": data.get("split"),
                "condition": data.get("condition"),
                "status": data.get("status"),
                "termination_reason": data.get("termination_reason"),
                "synthetic": bool(data.get("synthetic")),
            }
        )

    if not entries:
        print(f"ERROR: {batch} 下没有 episode.json", file=sys.stderr)
        return 2

    # 唯一槽位 = task × condition，且只允许本 split、本条件
    cfg = load_course_config()
    split_tasks = cfg.task_ids(args.split)
    seen: dict[tuple[str, str], list[str]] = {}
    foreign: list[dict] = []
    for entry in entries:
        if entry["split"] != args.split or entry["condition"] not in args.conditions:
            foreign.append(entry)
            continue
        key = (entry["task_id"], entry["condition"])
        seen.setdefault(key, []).append(entry["episode_path"])

    duplicates = {k: v for k, v in seen.items() if len(v) > 1}
    expected = {(t, c) for t in split_tasks for c in args.conditions}
    missing = sorted(expected - set(seen))
    extra = sorted(set(seen) - expected)

    out = Path(args.out) if args.out else batch / "index.jsonl"
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"index: {out.relative_to(REPO_ROOT) if out.is_relative_to(REPO_ROOT) else out}")
    print(f"episodes={len(entries)} slots={len(seen)} expected_slots={len(expected)}")
    print(f"  tasks={len(split_tasks)} conditions={','.join(args.conditions)}")
    if foreign:
        print(f"  排除 {len(foreign)} 条不属于本 split/条件的记录（仍写进索引尾部，便于核对）")
        for f in foreign[:5]:
            print(f"    {f['split']}/{f['condition']} {f['task_id']}")
    if duplicates:
        print(f"WARN 重复槽位 {len(duplicates)} 个（同一 task×condition 多条记录）:")
        for (task, cond), paths in list(duplicates.items())[:5]:
            print(f"  {cond} {task}: {len(paths)} 条 -> {paths}")
    if missing:
        print(f"WARN 缺 {len(missing)} 个槽位:")
        for task, cond in missing[:10]:
            print(f"  {cond} {task}")
    if extra:
        print(f"WARN {len(extra)} 个槽位不在 split 清单里:")
        for task, cond in extra[:10]:
            print(f"  {cond} {task}")

    if duplicates or missing or extra:
        return 1
    print("PASS: 槽位齐全且无重复")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
