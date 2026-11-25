"""运行记录自洽性检查（A 侧，只读）。

回答一个问题：**这批记录是不是一次完整、没被写坏的运行产出的**。
不做正确性判定（那是 C 的 scorer），只核对记录内部必须成立的关系：

1. 三件套齐全（episode.json / manifest.json / turns.jsonl）；
2. `manifest.task_id` == `episode.task_id`，`split/condition` 与目录一致；
3. `model_calls` == turns 行数；`input_tokens/output_tokens` == 逐行之和；
4. `turn_index` 从 0 连续；
5. `status=completed` ⇒ 有 final_answer；`no_answer` ⇒ final_answer 为 null；
6. 轮次不超过 12 + 1（最终轮）；
7. `wall_seconds` 不小于最后一轮的预算耗时（防两个并发作业写同一目录导致的混合记录）。

用法：

    python scripts/check_run_records.py runs/dev_full_v3
    python scripts/check_run_records.py runs/dev_full_v3 --allow-error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_jsonl(path: Path) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    problems: list[str] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            problems.append(f"turns.jsonl:{line_no} 不是合法 JSON（{exc.msg}）")
    return rows, problems


def check_episode(directory: Path, *, allow_error: bool) -> list[str]:
    problems: list[str] = []
    for name in ("episode.json", "manifest.json", "turns.jsonl"):
        if not (directory / name).is_file():
            problems.append(f"缺少 {name}")

    if problems:
        return problems

    episode = json.loads((directory / "episode.json").read_text(encoding="utf-8"))
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    turns, parse_problems = load_jsonl(directory / "turns.jsonl")
    problems.extend(parse_problems)

    if manifest.get("task_id") != episode.get("task_id"):
        problems.append("manifest.task_id 与 episode.task_id 不一致")
    if manifest.get("run_id") != episode.get("run_id"):
        problems.append("manifest.run_id 与 episode.run_id 不一致")

    parts = directory.parts
    split, condition = episode.get("split"), episode.get("condition")
    if split not in parts or condition not in parts:
        problems.append(f"split/condition（{split}/{condition}）与目录路径不符")

    status = episode.get("status")
    if status == "error":
        if not allow_error:
            problems.append(f"status=error：{episode.get('error')}")
    else:
        if episode.get("model_calls") != len(turns):
            problems.append(
                f"model_calls={episode.get('model_calls')} 但 turns 有 {len(turns)} 行"
            )
        indices = [t.get("turn_index") for t in turns]
        # 8be4109 起 1 起编号；更早批次 0 起。两种只认其一，且必须连续无重复。
        if indices != list(range(len(turns))) and indices != list(range(1, len(turns) + 1)):
            problems.append("turn_index 不是从 0 或 1 起连续编号")
        if episode.get("input_tokens") != sum(t.get("input_tokens", 0) for t in turns):
            problems.append("input_tokens 与逐行之和不一致")
        if episode.get("output_tokens") != sum(t.get("output_tokens", 0) for t in turns):
            problems.append("output_tokens 与逐行之和不一致")
        if status == "completed" and episode.get("final_answer") is None:
            problems.append("status=completed 但 final_answer 为 null")
        if status == "no_answer" and episode.get("final_answer") is not None:
            problems.append("status=no_answer 但 final_answer 非 null")
        if len(turns) > 13:
            problems.append(f"轮次 {len(turns)} 超过 12+1 上限")

        if turns:
            last_elapsed = (turns[-1].get("budget") or {}).get("elapsed_seconds")
            wall = episode.get("wall_seconds")
            if last_elapsed is not None and wall is not None and wall + 1.0 < last_elapsed:
                problems.append(
                    f"wall_seconds={wall} 小于最后一轮预算耗时 {last_elapsed}"
                    "（疑似两个作业写同一目录）"
                )

    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="检查运行记录自洽性")
    ap.add_argument("batch", help="批次目录，例如 runs/dev_full_v3")
    ap.add_argument("--allow-error", action="store_true", help="允许 status=error 的记录")
    args = ap.parse_args(argv)

    batch = Path(args.batch)
    if not batch.is_absolute():
        batch = REPO_ROOT / batch
    dirs = sorted({p.parent for p in batch.rglob("episode.json")})
    if not dirs:
        print(f"ERROR: {batch} 下没有 episode.json", file=sys.stderr)
        return 2

    bad = 0
    for directory in dirs:
        problems = check_episode(directory, allow_error=args.allow_error)
        if problems:
            bad += 1
            print(f"FAIL {directory.relative_to(batch).as_posix()}")
            for problem in problems:
                print(f"     - {problem}")

    print(f"episodes={len(dirs)} failed={bad}")
    if not bad:
        print("PASS: 记录自洽（三件套齐全、计数与 token 对得上、轮次连续）")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
