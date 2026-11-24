# D7 交接：完整 DEV 基线（32 次，统一协议）

给 B（做候选比较）与 C（审计/评分）的交接说明。数据在 `runs/dev_full_v4/`，不需要重新申请 GPU 就能用。

## 1. 这一批是什么

| 项 | 值 |
|---|---|
| 目录 | `runs/dev_full_v4/DEV/{A,B}/` |
| 记录数 | 32 = 16 DEV 任务 × 2 条件（A 官方输出反馈 / B trace-first），无遗漏无重复 |
| 代码提交 | `8be4109`（`fix(records): adopt the audit-facing turn schema and version triple`） |
| 模型 | `Qwen/Qwen3.5-4B` @ `851bf6e`，BF16，贪心解码，`enable_thinking=False` |
| 课程配置 hash | `configs/course/runtime_settings.json` = `faa7992…`（每条 `episode.json` 的 `config_sha256`） |
| 上游评测代码 | `third_party/code-act` @ `d607f56` |
| 作业 | 14100888（A，10:59）、14100889（B，09:27），debug 分区，各 1×A40 |
| 逐条版本三元组 | 每份 `episode.json` 自带 `code_commit` / `model_revision` / `config_sha256` |

**为什么又跑了一遍**：v3（`runs/dev_full_v3`）跑在 `c7145fa`，字段名与审计读取器不一致（`raw_text`/`tool_events`/`feedback_text`、缺少两个 final-answer 语义位、`turn_index` 从 0 起）。修正记录格式后重跑为 v4；**v4 与 v3 的 32 个最终答案逐条完全相同**（0 处差异），说明只是格式变化，行为未变。v3 保留作证据，不再用于分析。

## 2. 结果概览（仅结构 + 离线正确性，不含方法结论）

| 条件 | 记录 | 有最终答案 | 无答案 | 工具执行 | 工具被拦 | 模型调用 | 生成 token | 中位耗时 | 正确数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 16 | 16 | 0 | 152 | 16 | 141 | 15291 | 30.4 s | 10/16 (62.5%) |
| B | 16 | 15 | 1 | 102 | 1 | 114 | 12887 | 27.4 s | 13/16 (81.3%) |

- 唯一无答案是 B 的 `web_browsing/price_of_legendary_potion`（`no_answer_after_turns_exhausted`，12 轮用尽后的最终轮也没写出可解析答案），按课程规则保留、进分母。
- 终止原因：`answer`×22、`final_answer_after_turns_exhausted`×7、`final_answer_after_tokens_exhausted`×2、`no_answer_after_turns_exhausted`×1。
- 正确性来自 C 的 `scripts/score.py` + `references/offline_reference_v1.json`，输出 `runs/dev_full_v4/scored.jsonl`（`success` 与 `scoring_reason`）。

## 3. 180 秒与预算的可核对字段

`episode.json`：`task_started_at` / `task_deadline_at` / `task_seconds_limit` / `generation_stopped_at` / `generation_stopped_task_seconds` / `last_generation_finish_reason` / `episode_written_at` / `episode_written_task_seconds` / `post_generation_seconds` / `deadline_overrun_seconds` / `deadline_exceeded`。
`turns.jsonl`：每轮 `generation_seconds` / `finish_reason` / `cut_by_deadline` / `generation_stopped_at` / `generation_stopped_task_seconds`。

这批的读数：最大 `wall_seconds` = 122.7 s，最大 `generation_stopped_task_seconds` = 122.7 s，`deadline_exceeded` = 0，最大落盘延迟 `post_generation_seconds` = 0.016 s。**没有任何一次生成跨过 180 s**，所以截止截断分支在这一批里没有被真实触发（CPU 回归 `test_generate_receives_task_deadline` 与 `DeadlineBackend` 用例覆盖其语义）。

## 4. 自检命令（都能在本机跑，无 GPU）

```bash
# 结构 + 版本三元组 + 逐轮字段（C 的审计）
python scripts/audit_results.py --episodes runs/dev_full_v4/index.jsonl \
  --split DEV --conditions A B --out runs/dev_full_v4/audit.json \
  --expected-code-commit $(git rev-parse HEAD) \
  --expected-model-revision 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a \
  --expected-config-sha faa79929e12987fd301e07cb81d61e4b6ac4b87d4afce32de9b71229997dfdd1

# 统计表（有答案/无答案、blocked、中位耗时、逐任务 A/B）
python scripts/run_stats.py --runs runs/dev_full_v4/DEV

# 工具预算会计（按课程语义：blocked 不算执行）
python scripts/check_budget_accounting.py --runs runs/dev_full_v4/DEV

# 离线评分（需要 references/offline_reference_v1.json，见 docs/A_reference_export.md）
python scripts/score.py --episodes runs/dev_full_v4/index.jsonl \
  --references references/offline_reference_v1.json --out runs/dev_full_v4/scored.jsonl
```

## 5. 审计现状：2 个 error，均在计数口径上，需要 C 确认

`audit_results.py` 对 v4 报 2 个 error，全部集中在 `travel_itinerary_planning/multi_city_business_trip`：

| error | 数值 | 我的判读 |
|---|---|---|
| `tool_attempts_per_task_exceeded` | A 条件 `executed+blocked=48 > 32` | 执行恰好 32 次（到顶），另有 16 次是被拦的第 33+ 次调用；课程要求“不执行超限调用”，所以 48 = 32 执行 + 16 拦截 是合规形态 |
| `tool_attempts_per_action_exceeded` | B 条件第 2 轮 5 个事件 > 4 | 其中 4 个执行、1 个被拦，同样是块内第 5 次调用的拦截证据 |

`scripts/check_budget_accounting.py` 按“blocked 不算执行”的口径复核 32 条：254 次执行 / 17 次拦截，每轮执行 ≤ 4，每任务执行 ≤ 32，被拦事件均无 `result_repr`（确实没执行）→ PASS。

结论：这两个 error 是审计脚本把 `blocked` 计入上限导致的计数口径问题，不是运行记录违规。若 C 认可，建议把两处比较改成只统计 `execution_status != "blocked"`；在此之前，本批以 `check_budget_accounting.py` 的 PASS 为准。

## 6. 边界

- 只有 DEV，没有 EVAL；EVAL 必须等 B 的冻结包，本批不构成任何方法优劣结论。
- 硬件是 A40（debug 分区），与首轮 86 条基线同型号；贪心解码保证可复现，v3/v4 答案逐条一致即为证据。
- 单任务最多 32 次工具调用，A 条件有 16 次被拦（`multi_city_business_trip` 一个任务占满预算），说明该题对 A 条件的反馈信息量偏紧，值得 B 在候选设计时留意——但这只是观察，不是结论。
