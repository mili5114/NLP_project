"""核对系统提示里的工具签名与实际函数参数是否一致（A 侧，只读）。

课程附件 §3 要求提示里的签名与真实函数一致。适配层（`tasks._apply_course_signatures`）
只改写了审查点名的三个工具，其余工具可能还存在同类偏差——本脚本把 DEV+EVAL 全部任务、
全部工具扫一遍，报出"提示参数名 ≠ 真实参数名"的条目。

用法：

    python scripts/check_tool_signatures.py            # DEV + EVAL
    python scripts/check_tool_signatures.py --split DEV
    python scripts/check_tool_signatures.py --json out.json
"""

from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.runtime.config import load_course_config  # noqa: E402
from src.runtime.tasks import get_task  # noqa: E402

SIG_RE = re.compile(r"(\w+)\s*\(([^)]*)\)")


def prompted_params(fn_signature: str) -> list[str]:
    m = SIG_RE.search(fn_signature or "")
    if not m or not m.group(2).strip():
        return []
    params = []
    for raw in m.group(2).split(","):
        text = raw.split(":")[0].split("=")[0].strip()
        if text:
            params.append(text)
    return params


def actual_params(function) -> list[str] | None:
    """真实函数的参数名；内建函数（max/min/…）拿不到签名时返回 None，跳过比对。"""
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return None
    rendered = []
    for name, param in signature.parameters.items():
        if param.kind is inspect.Parameter.VAR_POSITIONAL:
            rendered.append("*" + name)
        elif param.kind is inspect.Parameter.VAR_KEYWORD:
            rendered.append("**" + name)
        else:
            rendered.append(name)
    return rendered


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="核对工具提示签名与真实函数")
    ap.add_argument("--split", nargs="+", default=["DEV", "EVAL"])
    ap.add_argument("--json", help="把明细写到 JSON")
    args = ap.parse_args(argv)

    cfg = load_course_config()
    rows: list[dict] = []
    checked = 0
    skipped = 0
    for split in args.split:
        for task_id in cfg.task_ids(split):
            task = get_task(task_id)
            for name, tool in task.tools.items():
                checked += 1
                prompted = prompted_params(tool.fn_signature)
                actual = actual_params(tool.function)
                if actual is None:
                    skipped += 1
                    continue
                if prompted != actual:
                    rows.append(
                        {
                            "split": split,
                            "task_id": task_id,
                            "tool": name,
                            "prompted": prompted,
                            "actual": actual,
                            "fn_signature": tool.fn_signature,
                        }
                    )

    print(
        f"tasks={sum(len(cfg.task_ids(s)) for s in args.split)} tools_checked={checked} "
        f"skipped_no_signature={skipped} mismatched={len(rows)}"
    )
    for row in rows:
        print(f"  {row['split']} {row['task_id']}")
        print(f"     {row['tool']}: 提示 {row['prompted']} != 真实 {row['actual']}")
    if args.json:
        Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
