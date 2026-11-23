# GPU Ledger (Contributor A)

*One row per Slurm job, including failed and cancelled ones. Data from `sacct`, 2026-11-23.*

| Job | Date | Partition | GPU | Elapsed | Purpose | Outcome |
|---|---|---|---|---|---|---|
| 14051595 | 11-22 | debug | a40 ×1 | 00:01:19 | Environment smoke test | COMPLETED |
| 14051965 | 11-22 | i64m1tga40u | a40 ×1 | 00:10:19 | First real episode (pilot; 1.3 tok/s era, recorded task_timeout) | COMPLETED |
| 14060163 | 11-22 | debug | a40 ×1 | 00:00:42 | Speed benchmark — crashed in `bench_speed.py` (tensor indexing bug) | FAILED |
| 14060276 | 11-22 | i64m1tga40u | a40 ×1 | 00:00:01 | Speed benchmark — died in 1 s: `sbatch --wrap` runs `/bin/sh`, which cannot `source` conda | FAILED |
| 14061564 | 11-22 | i64m1tga40u | a40 ×1 | 00:02:13 | Speed benchmark via proper `.sbatch`: confirmed 23.6–25.2 tok/s after FLA kernel install | COMPLETED |
| 14062952 | 11-22 | i64m1tga40u | — | 00:00:00 | Duplicate auto-submitted by the monitoring automation; cancelled before start | CANCELLED |
| 14062953 | 11-22 | i64m1tga40u | — | 00:00:00 | Duplicate auto-submitted by the monitoring automation; cancelled before start | CANCELLED |
| 14062955 | 11-22 | i64m1tga40u | a40 ×1 | 00:11:55 | Step 17: DEV 16 tasks, condition A (job chain 1/4) | COMPLETED |
| 14062956 | 11-22 | i64m1tga40u | a40 ×1 | 00:10:27 | Step 17: DEV 16 tasks, condition B (job chain 2/4) | COMPLETED |
| 14062957 | 11-22 | i64m1tga40u | a40 ×1 | 00:24:54 | Step 17: EVAL 27 tasks, condition A (auto-triggered after 14062955) | COMPLETED |
| 14062958 | 11-22 | i64m1tga40u | a40 ×1 | 00:17:19 | Step 17: EVAL 27 tasks, condition B (auto-triggered after 14062956) | COMPLETED |
| 14072303 | 11-23 | i64m1tga40u | a40 ×1 | pending | Reproducibility check: re-run DEV-B `interstellar_trade_transaction` into `runs/repro_check/` | PENDING |

## Totals

- GPU hours consumed (successful + failed, excluding the two cancelled jobs that never started): **≈ 1.32 GPU·h** on A40.
- Wasted GPU time (two failed benchmarks + the 1.3 tok/s pilot's slow path): ≈ 0.2 GPU·h — the pilot would have been ~10× faster with the kernel fix, which is exactly why it was root-caused before scaling up.
- Failures: 2 (both execution-harness bugs, fixed; neither touched course configuration).
