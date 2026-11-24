"""把一个运行批次的实际生效配置压成一个 hash（A 侧，只读 manifest.json）。

为什么要两个 hash：

* `course_hashes["runtime_settings.json"]`（也叫 `config_sha256`）= 课程给的
  `configs/course/runtime_settings.json` **文件内容**的 sha256。它只回答"课程设置有没有被改动"。
* `config_fingerprint` = **这次真正跑起来的东西**：课程 hash + 上游/团队 commit +
  模型 revision + 解码设置 + 全部 limits + 停止串 + 解释器/框架版本。

同一个课程 hash 可以对应不同的实际运行（比如代码 commit 不同、模型 revision 不同），
所以交接口径要分开写，不能拿课程 hash 当"完整配置 hash"。

用法：

    python scripts/config_fingerprint.py runs/dev_full_v3/DEV
    python scripts/config_fingerprint.py runs/dev_full_v3/DEV --expect <hash>   # 不一致则退出码 1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]

# 只取与"实际执行"有关的字段；run_id / task_id / condition / 时间戳等每次不同，不能进 hash。
VOLATILE_KEYS = {
    "run_id",
    "task_id",
    "tasks",
    "split",
    "condition",
    "started_at",
    "aborted",
}


def canonical_fingerprint(manifest: dict[str, Any]) -> str:
    cfg = {k: v for k, v in manifest.items() if k not in VOLATILE_KEYS}
    hashes = {k: v for k, v in cfg.get("course_hashes", {}).items() if not k.startswith("_")}
    cfg["course_hashes"] = hashes
    blob = json.dumps(cfg, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def iter_manifests(root: Path) -> Iterable[Path]:
    yield from sorted(root.rglob("manifest.json"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="计算运行批次的完整配置 fingerprint")
    ap.add_argument("runs", help="批次目录，例如 runs/dev_full_v3/DEV")
    ap.add_argument("--expect", help="期望的 fingerprint；不一致则退出码 1")
    ap.add_argument("--show", action="store_true", help="打印参与 hash 的规范化内容")
    args = ap.parse_args(argv)

    root = Path(args.runs)
    if not root.is_absolute():
        root = REPO_ROOT / root
    if not root.exists():
        print(f"ERROR: {root} 不存在", file=sys.stderr)
        return 2

    seen: dict[str, list[str]] = {}
    example: dict[str, Any] | None = None
    for path in iter_manifests(root):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        fp = canonical_fingerprint(manifest)
        seen.setdefault(fp, []).append(str(path.relative_to(root).parent))
        example = example or manifest

    if not seen:
        print(f"ERROR: {root} 下没有 manifest.json", file=sys.stderr)
        return 2
    if example is None:  # pragma: no cover - 类型收窄
        return 2

    print(f"manifests={sum(len(v) for v in seen.values())} distinct_fingerprints={len(seen)}")
    for fp, paths in seen.items():
        print(f"  {fp}  x{len(paths)}")
        for p in paths[:3]:
            print(f"      {p}")
        if len(paths) > 3:
            print(f"      … 其余 {len(paths) - 3} 条")

    course_hashes = {
        k: v for k, v in example.get("course_hashes", {}).items() if not k.startswith("_")
    }
    print("course_hashes（课程文件内容 hash）:")
    for name, value in course_hashes.items():
        print(f"  {name}: {value}")
    print(f"team_commit={example.get('team_commit')} upstream_commit={example.get('upstream_commit')}")
    print(f"model_revision={(example.get('model') or {}).get('revision')}")

    if args.show:
        cfg = {k: v for k, v in example.items() if k not in VOLATILE_KEYS}
        cfg["course_hashes"] = course_hashes
        print(json.dumps(cfg, sort_keys=True, ensure_ascii=False, indent=2))

    if len(seen) != 1:
        print("ERROR: 同一批次里出现多个 fingerprint（协议不统一，不能当同一批基线）", file=sys.stderr)
        return 1
    if args.expect:
        actual = next(iter(seen))
        if actual != args.expect:
            print(f"ERROR: fingerprint 不符：期望 {args.expect} 实际 {actual}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
