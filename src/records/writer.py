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

    def close(self, episode: dict[str, Any]) -> Path:
        if self._turns_fh is not None:
            self._turns_fh.close()
            self._turns_fh = None
        payload = {
            "schema_version": SCHEMA_VERSION,
            "trajectory_path": str(self.turns_path.as_posix()),
            "wall_seconds": round(time.time() - self._started, 3),
            **episode,
        }
        out = self.dir / "episode.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return out
