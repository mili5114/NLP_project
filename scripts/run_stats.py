"""把一次运行目录汇总成可核对的中文统计表（A 侧，只读 episode.json）。

用途：
* 交 B/C 之前的自检（是否有无答案、超时、blocked 是否只在预算语义内）；
* 报告里的“结果概览”数字直接从这里的输出抄，避免手抄出错；
* 不做正确性判定——那需要离线参考文件，属 C 的 scorer。

用法：

    python scripts/run_stats.py --runs runs/dev_full_v3/DEV
    python scripts/run_stats.py --runs runs/dev_full_v3/DEV --out runs/dev_full_v3/stats.md
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_episodes(root: Path, split: str | None) -> tuple[list[dict[str, Any]], int]:
    """返回 (episodes, skipped)。`pilot_*` 目录是历史留档，不参与统计。"""
    episodes = []
    skipped = 0
    for path in sorted(root.rglob("episode.json")):
        if any(part.startswith("pilot_") for part in path.parts):
            skipped += 1
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("synthetic"):
            skipped += 1
            continue
        if split and data.get("split") != split:
            skipped += 1
            continue
        data["_path"] = path
        episodes.append(data)
    return episodes, skipped


def _median(values: list[float]) -> float:
    return round(statistics.median(values), 1) if values else 0.0


def summarize(episodes: list[dict[str, Any]]) -> str:
    by_cond: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ep in episodes:
        by_cond[ep["condition"]].append(ep)

    lines: list[str] = []
    lines.append("| 条件 | 记录数 | 有最终答案 | 无答案 | 工具执行 | 工具被拦 | 模型调用 | 生成 token | 中位耗时 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for cond in sorted(by_cond):
        eps = by_cond[cond]
        answered = sum(1 for e in eps if e.get("final_answer") is not None)
        executed = sum(int(e.get("tool_attempts_executed", 0)) for e in eps)
        blocked = sum(int(e.get("tool_attempts_blocked", 0)) for e in eps)
        calls = sum(int(e.get("model_calls", 0)) for e in eps)
        tokens = sum(int(e.get("output_tokens", 0)) for e in eps)
        wall = _median([float(e.get("wall_seconds", 0)) for e in eps])
        lines.append(
            f"| {cond} | {len(eps)} | {answered} | {len(eps) - answered} | {executed} | {blocked} "
            f"| {calls} | {tokens} | {wall}s |"
        )

    reasons = Counter(e.get("termination_reason") or "None" for e in episodes)
    lines.append("")
    lines.append("终止原因：" + "、".join(f"`{k}`×{v}" for k, v in sorted(reasons.items())))

    tasks = sorted({e["task_id"] for e in episodes})
    lines.append("")
    lines.append("| 任务 | A 状态/耗时 | B 状态/耗时 | A 调用 | B 调用 |")
    lines.append("|---|---|---|---:|---:|")
    index = {(e["task_id"], e["condition"]): e for e in episodes}

    def cell(ep: dict[str, Any] | None) -> str:
        if ep is None:
            return "—"
        answer = "有答案" if ep.get("final_answer") is not None else "无答案"
        return f"{ep.get('status')}/{answer}/{round(float(ep.get('wall_seconds', 0)), 1)}s"

    for task in tasks:
        a = index.get((task, "A"))
        b = index.get((task, "B"))
        lines.append(
            f"| `{task}` | {cell(a)} | {cell(b)} "
            f"| {a.get('model_calls') if a else '—'} | {b.get('model_calls') if b else '—'} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="汇总运行目录的 episode 统计")
    parser.add_argument("--runs", nargs="+", required=True, help="运行根目录（可多个）")
    parser.add_argument("--split", default=None, help="只统计某个 split（默认全部）")
    parser.add_argument("--out", default=None, help="写入 markdown 文件（默认打印到 stdout）")
    args = parser.parse_args(argv)

    roots = [Path(r) if Path(r).is_absolute() else REPO_ROOT / r for r in args.runs]
    episodes: list[dict[str, Any]] = []
    skipped = 0
    for root in roots:
        if not root.exists():
            raise SystemExit(f"路径不存在：{root}")
        found, skip = load_episodes(root, args.split)
        episodes.extend(found)
        skipped += skip
    if not episodes:
        raise SystemExit("没有找到 episode.json")

    text = summarize(episodes)
    if skipped:
        text += f"\n（已跳过 {skipped} 条：pilot 留档 / synthetic / 其他 split）\n"
    if args.out:
        out = Path(args.out) if Path(args.out).is_absolute() else REPO_ROOT / args.out
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out.relative_to(REPO_ROOT)} ({len(episodes)} episodes)")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
