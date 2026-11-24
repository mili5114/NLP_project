"""运行记录写入。

一个 episode = 一个 task × 一个 condition，目录里三个文件：
- manifest.json  这次运行的全部固定条件（可独立复现）
- turns.jsonl    每次模型调用一行（含最终回答调用）
- episode.json   这次运行的结论性字段（供 C 汇总）

`reference_answer` / `success` 一律不写：在线记录不许出现标准答案。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1"


class EpisodeWriter:
    def __init__(
        self,
        root: Path,
        *,
        run_id: str,
        slug: str,
        split: str,
        condition: str,
        manifest: dict[str, Any],
    ) -> None:
        self.dir = Path(root) / split / condition / slug
        self.dir.mkdir(parents=True, exist_ok=True)
        self.manifest = manifest
        self.turns_path = self.dir / "turns.jsonl"
        self._turns_fh = None
        self._started = time.time()
        self.turn_count = 0

    def open(self) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
            **self.manifest,
        }
        (self.dir / "manifest.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self._turns_fh = self.turns_path.open("w", encoding="utf-8")

    def write_turn(self, turn: dict[str, Any]) -> None:
        if self._turns_fh is None:
            raise RuntimeError("writer 未 open()")
        record = {"turn_index": self.turn_count, **turn}
        self._turns_fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._turns_fh.flush()
        self.turn_count += 1

    def close(
        self,
        episode: dict[str, Any],
        *,
        timings: dict[str, Any] | None = None,
        written_at: float | None = None,
    ) -> Path:
        """`timings` 里放"生成停止/落盘"时间戳（由 runner 提供）。

        课程 180s 是任务截止时间；185s 只是包含停止、同步、落盘的工程检查线。
        因此记录里必须能分开这两件事：墙钟总时长 `wall_seconds` 不等于生成耗时。
        """
        if self._turns_fh is not None:
            self._turns_fh.close()
            self._turns_fh = None
        written = time.time() if written_at is None else written_at
        payload = {
            "schema_version": SCHEMA_VERSION,
            "trajectory_path": str(self.turns_path.as_posix()),
            "wall_seconds": round(written - self._started, 3),
            **(timings or {}),
            **episode,
        }
        out = self.dir / "episode.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return out
