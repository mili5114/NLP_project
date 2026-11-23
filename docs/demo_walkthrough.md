# Demonstration Walkthrough (15 minutes, platform portion)

*Contributor A's part of the Task 7 demonstration. The course requires showing the same task under different feedback conditions, highlighting changes in model-visible feedback and subsequent actions. Strategy commentary (B) and scoring commentary (C) are separate segments owned by B and C; slots are marked below.*

Format decision: record-walkthrough based (no live cluster submission on stage — queue wait times are uncontrollable on a shared cluster). All materials referenced below are committed in the repository.

## Segment 1 — Architecture overview (2 min)

One diagram: task prompt → model generates code block → parser extracts action → tools execute in the IPython shell → observer records events → feedback builder (A or B) composes the next turn's input → repeat until first final answer or budget exhaustion.

Key sentence: everything except the feedback builder is byte-identical across conditions; that is what makes the comparison fair.

## Segment 2 — Five implementation layers (4 min)

1. **Backend** (`src/runtime/backend.py`): local Qwen3.5-4B, BF16, greedy; warmup absorbs Triton JIT; emits real token counts.
2. **REPL** (`src/runtime/repl.py`): one IPython shell per task, variables persist across turns, reset between tasks — demonstrated by CPU test `test_variables_reset_between_tasks`.
3. **Observer** (`src/runtime/observer.py`): 7 fields per tool call; caps 4 per block / 32 per task; over-cap calls are blocked-but-recorded.
4. **Budget** (`src/runtime/budget.py`): every limit read from course config, checksum-verified at startup.
5. **Records** (`src/records/writer.py`): three-record format; `manifest.json` pins the environment of every single episode.

## Segment 3 — Sample walkthrough (4 min)

Use `runs/dev_baselines/DEV/A/trade_calculator_interstellar_trade_transaction*/` (the Task 1 annotated sample):

- 6 turns, 4 chained tool calls, final answer 8100.0.
- Show input-token growth 701→1105→1203→1281→1359→1440 as direct evidence that tool results re-enter the prompt each turn.
- Point out turn 0 as a natural "invalid generation" case (thinking without an Action block → protocol error feedback).

## Segment 4 — A/B on the same task (2 min, the course-required core)

Side-by-side of the same task under condition A and condition B (`runs/dev_baselines/DEV/A/` vs `DEV/B/`):

- Diff `feedback_text` per turn: B prepends the execution trace ahead of the official output within the same 2000-character cap.
- Highlight one turn where the subsequent action differs, and trace how that difference came from what the model could see.

*[Slot for B: why the trace-first design, what changes were expected.]*

## Segment 5 — Platform diagnostics story (3 min)

The 20x slowdown incident: symptom (1.3 tok/s → 180 s budget = 2 turns) → root cause (missing `flash-linear-attention` kernel → pure-PyTorch fallback; one-time Triton JIT charged to the first task) → fix (kernel install + load-time warmup) → verification (23.6–25.2 tok/s; 86 episodes, zero timeouts, max wall time 130 s vs the 180 s limit).

## Segment 6 — Handoff (2 min)

- GPU ledger: ≈1.32 GPU·h total including 2 failed and 2 cancelled jobs (`docs/gpu_ledger.md`).
- Everything reproducible from the repository alone: pinned revisions, lock file, checksum-verified configs, committed records (`runs/index.md`).
- Reproducibility check: the same task re-run under identical config lands in `runs/repro_check/` (job 14072303).

*[Slot for C: scorer, aggregation, and whether the strategy was effective; one proposed future experiment.]*

## Timing budget

| Segment | Minutes |
|---|---|
| 1 Architecture | 2 |
| 2 Layers | 4 |
| 3 Sample | 4 |
| 4 A/B diff | 2 |
| 5 Diagnostics | 3 |
| 6 Handoff | 2 (+B/C slots inside) |
| **Total** | **17 incl. slots → trim to 15 by tightening 2 and 5 if B/C take their slots** |
