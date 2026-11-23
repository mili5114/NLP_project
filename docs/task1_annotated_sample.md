# Task 1 Deliverable: Annotated Interaction Record (Environment Familiarization)

> Source episode: `DEV-A-trade_calculator_interstellar_trade_transaction-s4051`
> Produced on A40 by Slurm job `14062955` (2026-11-23); records committed at `95ce5b0` under
> `runs/dev_baselines/DEV/A/trade_calculator_interstellar_trade_transaction_DEV-A-…-s4051/`.
> Chosen because it exercises four different tools in a chain and ends with a clean final answer —
> the shortest complete demonstration of the CodeAct workflow we run.

## 1. The five elements Task 1 asks to identify

| Element | In this episode | Where in the records |
|---|---|---|
| Task instruction | "…exchanging 100 units of space ore… base price 50 credits/unit, conversion rate 1.5, tariff 8%" | `turns.jsonl` line 1 → `messages[-1].content` (the user message; tool list is the system message) |
| Generated code action | `calculator("100 * 50")`, then `convert_currency(5000, 1.5)`, `calculate_tariff(7500.0, 8)`, `estimate_final_value(7500.0, 600.0)` | `turns.jsonl` → `action` (verbatim code sent to the interpreter) |
| Tool return | 5000 → 7500.0 → 600.0 → 8100.0 | `turns.jsonl` → `tool_events[*].result_repr` and `python_output` |
| Model-visible feedback | `Out[1]: 5000` / `Out[1]: 7500.0` / `Out[1]: 600.0` / `Out[1]: 8100.0` | `turns.jsonl` → `feedback_text` (condition A = execution output verbatim) |
| Final answer | `Answer: 8100.0` | `episode.json` → `final_answer`; `turns.jsonl` last line → `raw_text` |

## 2. Turn-by-turn walkthrough

**T0 — model talks, no action.** Input 701 tokens (system = tool list with signatures, user = task).
The model produced chain-of-thought planning but no `Action:`/`Answer:` marker.
`parsed = {"type": "invalid", …}`. The runner does not guess or repair: it appends the
canonical error line — *"Invalid generation. Your output should contain either 'Action:' or
'Answer:'"* — as feedback, consuming 1 of the 12 interaction rounds. This is the official
termination/parse semantics, preserved unchanged in our runner.

**T1 — first code action.** Action `calculator("100 * 50")`. The observer recorded
`(tool=calculator, execution_status=ok, result_repr=5000, elapsed=1e-05s)`. Python output:
`Out[1]: 5000`. Feedback for the next turn = that output, verbatim (condition A).

**T2–T4 — the tool chain.** Each turn, the model reads the previous number from feedback and
feeds it into the next tool: `convert_currency(5000, 1.5)` → 7500.0;
`calculate_tariff(7500.0, 8)` → 600.0; `estimate_final_value(7500.0, 600.0)` → 8100.0.
Note the input-token growth per turn: 701 → 1105 → 1203 → 1281 → 1359 → 1440 — the context
grows by exactly (previous tokens + action + feedback), which is the direct evidence that
execution results become part of the next model input.

**T5 — final answer.** `Answer: 8100.0`. The budget state machine accepted the first parseable
answer and stopped (`termination_reason = "answer"`). Totals: 6 model calls, 7089 input /
677 output tokens, 28.4 s wall — far inside the 12-round / 3072-token / 180-s budget.

## 3. How Python code invokes tools (and how we count)

Tools are ordinary Python functions injected into the task's namespace (`task._ns`); the model's
code action calls them exactly like any function. Because actions are code, the same call can
appear once in the text yet execute many times inside a loop — so counting tool calls from the
text would be wrong. Our `ToolObserver` wraps every tool function at its entry point and records
a 7-field event (index/tool/args/kwargs/execution_status/result/elapsed) per call, enforcing the
course limits (4 per code block, 32 per task; over-limit calls are *blocked but preserved*).
In this episode every call was under limit, so all 4 events are `ok`.

## 4. Variable persistence and cross-task reset

- **Within a task, the interpreter is one persistent IPython shell.** `runner.py` creates a
  single `BlockExecutor` per task (line 92) and every turn runs in that same shell
  (`repl.run(...)`), so assignments survive across turns by construction.
  The constant `Out[1]` in outputs is *not* evidence of a fresh shell: we run cells with
  `store_history=False`, which prevents the In/Out counter from advancing.
  Other episodes show real cross-turn variable use, e.g.
  `runs/dev_baselines/DEV/A/trade_calculator_optimizing_bulk_purchase_discounts…/` T1 assigns
  `base_price_A`, `total_price_A_950`, `final_value_A_950` and keeps extending the same script.
- **Between tasks everything is dropped.** Each episode constructs a fresh executor on a fresh
  task namespace; `BlockExecutor.reset()` (`shell.reset(new_session=True)`) is the belt-and-braces
  reset. This is covered by the CPU test `test_variables_reset_between_tasks`: a variable defined
  in episode 1 raises `NameError` in episode 2.

## 5. Record format (what B/C can rely on)

Per episode directory: `episode.json` (summary: status, termination_reason, final_answer,
model_calls, token totals, wall time, config SHA-256), `turns.jsonl` (one JSON object per model
call: messages, raw_text, parsed action, python_output, tool_events, feedback_text,
feedback_metadata, budget), `manifest.json` (run identity). Scoring must be offline: the records
contain the model's prediction only — `expected_output` never enters the context (verified by
CPU test `test_no_reference_leak`).

## 6. Reproduce

```bash
sbatch -p i64m1tga40u --gres=gpu:a40:1 \
  --export=ALL,SPLIT=DEV,COND=A,TASKS=trade_calculator/interstellar_trade_transaction \
  scripts/env/gpu_job.sbatch
# → runs/dev_baselines/DEV/A/<run_id>/{episode.json, manifest.json, turns.jsonl}
```

## 面试口径（中文，备考用）

1. **五个要素各在哪个字段**：任务指令在 `messages` 的 user 消息、代码动作在 `action` 字段、
   工具返回在 `tool_events` 的 `result_repr`、模型可见反馈在 `feedback_text`、最终答案在
   `episode.json` 的 `final_answer`。
2. **执行结果怎么进入下一次模型输入**：上一轮的执行输出（条件 A 原样、条件 B trace-first）
   作为 feedback 追加进 messages，输入 token 逐轮增长（701→1440）就是证据。
3. **变量持久与任务间重置**：同一任务共用一个 IPython shell（`Out[1]` 恒定是因为
   `store_history=False`，不是每轮新建）；任务之间整体重建 + `reset(new_session=True)`，
   CPU 测试 `test_variables_reset_between_tasks` 用 NameError 证明隔离。
4. **为什么数工具调用要包函数**：代码动作是程序，循环里一行文本能执行一百次；只有拦在
   函数入口的计数才是真实执行次数。

> **Sample confirmed** by SibeiLYU, 2026-11-23: interstellar_trade_transaction (DEV-A) is the Task 1 annotated sample.
