"""在线记录答案隔离检查：任何 episode 记录里都不许出现参考答案的痕迹。

课程附件 §2：参考答案只用于离线评分，不得进入模型输入、模型可见反馈或代码执行环境。
这里用“痕迹扫描”来证明隔离，而不是只看代码意图：

* `Expected Output:` —— 上游 `Task.print_task()` 的打印标记，一旦被落盘就说明答案进了日志；
* `expected_output` / `is_correct` / `reference_answer` —— 参考答案相关字段名；
* 命中即非零退出，并打印文件与行号，便于定位是哪一环泄漏。

用法：

    python scripts/check_answer_isolation.py                  # 扫描 runs/
    python scripts/check_answer_isolation.py --runs runs/dev_full_v3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MARKERS = ("Expected Output:", "expected_output", "is_correct", "reference_answer")
TARGET_SUFFIXES = (".json", ".jsonl")


def iter_episode_files(root: Path) -> list[Path]:
    """只扫描真正的运行记录目录（包含 episode.json 的那一层），跳过索引与脚本。"""
    episode_dirs = {p.parent for p in root.rglob("episode.json")}
    files: list[Path] = []
    for directory in sorted(episode_dirs):
        files.extend(sorted(q for q in directory.iterdir() if q.suffix in TARGET_SUFFIXES))
    return files


def scan(files: list[Path]) -> list[tuple[Path, int, str, str]]:
    hits: list[tuple[Path, int, str, str]] = []
    for path in files:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line_no, line in enumerate(fh, 1):
                for marker in MARKERS:
                    if marker in line:
                        hits.append((path, line_no, marker, line.strip()[:160]))
                        break
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查运行记录里是否出现参考答案痕迹")
    parser.add_argument(
        "--runs", nargs="+", default=["runs"], help="要扫描的根目录（默认 runs）"
    )
    args = parser.parse_args(argv)

    roots = [Path(r) if Path(r).is_absolute() else REPO_ROOT / r for r in args.runs]
    for root in roots:
        if not root.exists():
            raise SystemExit(f"路径不存在：{root}")

    files: list[Path] = []
    for root in roots:
        files.extend(iter_episode_files(root))

    if not files:
        raise SystemExit("没有找到任何 episode.json，扫描范围可能指错了目录")

    hits = scan(files)
    episodes = {p.parent for p in files}
    print(f"scanned {len(files)} files in {len(episodes)} episode dirs")
    if hits:
        print(f"FAIL: {len(hits)} hit(s)")
        for path, line_no, marker, snippet in hits[:20]:
            print(f"  {path.relative_to(REPO_ROOT)}:{line_no} [{marker}] {snippet}")
        return 1
    print("PASS: no reference-answer trace in online records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
