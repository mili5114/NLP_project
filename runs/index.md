# Run Index

*Every run directory in this repository, what produced it, and how to read it.*

| Directory | Episodes | Produced by | Notes |
|---|---|---|---|
| `runs/dev_baselines/DEV/A/` | 16 | Job 14062955 (11-22) | First-round baseline, condition A |
| `runs/dev_baselines/DEV/B/` | 16 | Job 14062956 (11-22) | First-round baseline, condition B |
| `runs/dev_baselines/DEV/A/pilot_14051965/` | 1 | Job 14051965 (11-22) | Kept for the record: pilot run during the 1.3 tok/s era; its `task_timeout` is an artifact of the missing FLA kernel, not a protocol result |
| `runs/eval_baselines/EVAL/A/` | 27 | Job 14062957 (11-22) | Evaluation set, condition A |
| `runs/eval_baselines/EVAL/B/` | 27 | Job 14062958 (11-22) | Evaluation set, condition B |
| `runs/repro_check/` | 1 | Job 14072303 (11-23) | Reproducibility check: DEV-B `interstellar_trade_transaction` re-run; compare against the DEV-B baseline episode |

## Record format (per episode directory)

- `episode.json` — outcome: status, termination reason, final answer, model calls, token counts, tool attempt counts (executed/blocked), wall seconds.
- `manifest.json` — environment fingerprint: config SHA-256 hashes, model revision, git commit.
- `turns.jsonl` — one JSON object per turn: full messages, raw generation text, parse result, tool events (7 fields each), feedback text, budget state.

## Reading recipes

- 整目录统计（有答案/无答案、终止原因、blocked、中位耗时、逐任务 A/B）：`python scripts/run_stats.py --runs runs/dev_full_v3/DEV`（`pilot_*` 目录自动跳过）。
- Task A/B comparison for the demo: `runs/dev_baselines/DEV/A/*<task>*` vs `runs/dev_baselines/DEV/B/*<task>*`, diff the `feedback_text` fields turn by turn.
- Failure classification: see `docs/failure_taxonomy.md`.
- Environment provenance of any episode: read its `manifest.json`, cross-check against `configs/versions.json`.
