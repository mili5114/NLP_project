# Code Map (module level)

*What lives where in this repository, and who wrote it. Line counts as of commit `a50451e` (2026-11-23).*

## Execution platform — Contributor A

| Module | Lines | Responsibility | Key entry points |
|---|---|---|---|
| `src/runtime/config.py` | 159 | Loads the three course configuration files and verifies their SHA-256 checksums at startup; a mismatch aborts the run | `load_config()` |
| `src/runtime/backend.py` | 180 | Model backends: `FakeBackend` (deterministic, for CPU tests) and `TransformersBackend` (local Qwen3.5-4B, BF16, greedy). Emits real token counts and wall-clock seconds per turn. Fires an 8-token warmup generation at load to absorb one-time Triton JIT compilation | `load()`, `generate()` |
| `src/runtime/repl.py` | 98 | IPython 8.37 interactive shell wrapper. One shell per task, variables persist across turns (`store_history=False` keeps the `Out[n]` counter constant); reset between tasks | `run_cell()`, `reset()` |
| `src/runtime/observer.py` | 163 | Tool-event observer: records 7 fields per tool call (index, tool, args, kwargs, execution status, result, elapsed). Enforces caps of 4 calls per code block and 32 per task; over-cap calls are blocked (recorded, not executed) | `wrap()`, event emission |
| `src/runtime/budget.py` | 89 | Budget state machine: rounds (12+1), completion tokens (3072), context (16384), task seconds (180), code-block seconds (15). All values read from course config, never hardcoded | `Budget` |
| `src/runtime/tasks.py` | 75 | Dataset access with answer isolation: redirects `stdout` during task load so `print_task` cannot leak the expected output to the agent or into the transcript | `ensure_importable()`, `get_task()` |
| `src/feedback/baselines.py` | 141 | Feedback builders for the two conditions. A: official task output verbatim. B: execution trace prepended ahead of the official output, same 2000-char cap | `build_feedback_a/b()` |
| `src/feedback/dispatcher.py` | 60 | Selects the feedback builder from the `--condition` flag | `get_feedback_builder()` |
| `src/records/writer.py` | 71 | Writes the three-record format per episode: `episode.json`, `manifest.json`, `turns.jsonl` | `EpisodeWriter` |
| `src/runtime/runner.py` | 463 | CLI entry point and per-task orchestration; a per-task exception guard prevents one failing task from aborting the batch | `main()`, `run_task()` |
| `tests/test_runtime_cpu.py` | 228 | 14 CPU-only tests: answer isolation, budget semantics, observer caps, records, condition parity, variable reset between tasks | `python -m unittest` |

## Offline evaluation toolchain — Contributor C (merged via PR #2)

| Module | Lines | Responsibility |
|---|---|---|
| `src/evaluation/scoring.py` | 150 | Offline scorer (answer matching against reference outputs) |
| `src/evaluation/aggregation.py` | 378 | Aggregation semantics: denominators, token means, A/B pairing |
| `src/evaluation/audit.py` | 451 | Completeness auditing over run directories and the turns reader adapter |
| `src/evaluation/io.py` | 265 | Run-directory input/output |
| `src/evaluation/turns_reader.py` | 132 | Adapter reading `turns.jsonl` into evaluation structures |
| `src/evaluation/plots.py` | 99 | Plot generation |
| `tests/test_scoring.py` / `test_aggregation.py` / `test_audit.py` | 146/236/316 | Boundary tests for the above |

## Environment and operations — Contributor A

| Path | Purpose |
|---|---|
| `scripts/env/setup_env.sh` | Reproducible conda environment from the lock file |
| `scripts/env/fetch_model.sh` / `fetch_model.py` | Model download via ModelScope mirror (hf-mirror was 30x slower), hash verification |
| `scripts/env/check_env.py` | Environment self-check (versions, module presence) |
| `scripts/env/bench_speed.py` / `bench.sbatch` | Decoding-speed benchmark; traced the 1.3 tok/s slowdown to the missing FLA kernel |
| `scripts/env/gpu_job.sbatch` | Slurm job template (SPLIT/COND/TASKS/RUNS_ROOT env-driven) |
| `configs/versions.json`, `configs/model_provenance.json` | Version pinning and model provenance |
| `configs/course/` | Course-issued configuration, read-only, checksum-verified |

## Reports and analysis documents

| Path | Purpose |
|---|---|
| `report/sections/00_background_setup.md` | Contributor A's report chapter (motivation + setup) |
| `docs/failure_taxonomy.md` | Step 19: classification of failures across 86 episodes |
| `docs/task1_annotated_sample.md` | Step 16: annotated interaction record for course Task 1 |
| `docs/gpu_ledger.md` | Step 21: GPU hours ledger (including failed/cancelled jobs) |
| `docs/demo_walkthrough.md` | Step 20: 15-minute demonstration outline (platform portion) |
| `runs/index.md` | Step 21: index of run directories |
