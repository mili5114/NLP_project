"""预算会计检查：按课程语义核对“执行”与“被拦”，而不是把两者相加。

课程附件 §2：每个代码块最多 4 次工具调用、每个任务最多 32 次；超出上限的调用
**不执行**但保留前面效果。因此一份合规记录必然出现 `executed + blocked > 32`
或某一轮 `len(events) > 4`——多出来的只能是被拦的那部分。

C 的 `audit_results.py` 目前把 `executed + blocked` 与 `len(events)` 直接对上
限比较，会把这种合规证据判成错误（v4: `multi_city_business_trip` A 48>32、
B 第 2 轮 5>4）。本脚本按正确读数复核，输出可贴进交接说明的数字。

用法：

    python scripts/check_budget_accounting.py --runs runs/dev_full_v4/DEV
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.runtime.config import load_course_config  # noqa: E402

BLOCKED = "blocked"


def check_episode(ep_dir: Path, limits: Any) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    stats = {"turns": 0, "executed": 0, "blocked": 0, "max_events_per_turn": 0}
    episode = json.loads((ep_dir / "episode.json").read_text(encoding="utf-8"))
    turns_path = ep_dir / "turns.jsonl"
    turns = [json.loads(line) for line in turns_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    stats["turns"] = len(turns)

    for turn in turns:
        events = turn.get("events") or []
        executed = [e for e in events if e.get("execution_status") != BLOCKED]
        blocked = [e for e in events if e.get("execution_status") == BLOCKED]
        stats["executed"] += len(executed)
        stats["blocked"] += len(blocked)
        stats["max_events_per_turn"] = max(stats["max_events_per_turn"], len(events))
        if len(executed) > limits.tool_attempts_per_action and not turn.get("is_final_answer_turn"):
            errors.append(
                f"turn {turn['turn_index']}: {len(executed)} executed calls > "
                f"{limits.tool_attempts_per_action} per block"
            )
        for event in blocked:
            if event.get("result_repr") is not None:
                errors.append(
                    f"turn {turn['turn_index']}: blocked call {event.get('index')} has a result "
                    "(should not have executed)"
                )

    if stats["executed"] > limits.tool_attempts_per_task:
        errors.append(f"executed={stats['executed']} > {limits.tool_attempts_per_task} per task")
    for field, key in (("tool_attempts_executed", "executed"), ("tool_attempts_blocked", "blocked")):
        declared = episode.get(field)
        if declared is not None and int(declared) != stats[key]:
            errors.append(f"{field}={declared} != counted {stats[key]}")
    return errors, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按课程语义检查工具预算会计")
    parser.add_argument("--runs", nargs="+", default=["runs"], help="运行根目录（默认 runs）")
    args = parser.parse_args(argv)

    limits = load_course_config().limits
    roots = [Path(r) if Path(r).is_absolute() else REPO_ROOT / r for r in args.runs]
    dirs = sorted({p.parent for root in roots for p in root.rglob("episode.json")})
    if not dirs:
        raise SystemExit("没有找到 episode.json")

    problems: list[str] = []
    totals: Counter[str] = Counter()
    for ep_dir in dirs:
        errors, stats = check_episode(ep_dir, limits)
        totals.update({k: v for k, v in stats.items() if k != "max_events_per_turn"})
        totals["max_events_per_turn"] = max(totals["max_events_per_turn"], stats["max_events_per_turn"])
        for err in errors:
            problems.append(f"{ep_dir.parent.name}/{ep_dir.name}: {err}")

    print(f"episodes={len(dirs)} turns={totals['turns']} executed={totals['executed']} "
          f"blocked={totals['blocked']} max_events_per_turn={totals['max_events_per_turn']}")
    if problems:
        print(f"FAIL: {len(problems)} problem(s)")
        for p in problems[:20]:
            print("  " + p)
        return 1
    print(
        f"PASS: executed<= {limits.tool_attempts_per_action}/block and "
        f"<= {limits.tool_attempts_per_task}/task; blocked calls never executed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
