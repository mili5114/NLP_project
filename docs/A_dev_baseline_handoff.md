# D7 交接：完整 DEV 基线（32 次，统一协议）

给 B（做候选比较）与 C（审计/评分）的交接说明。数据在 `runs/dev_full_v5/`，不需要重新申请 GPU 就能用。

## 1. 这一批是什么

| 项 | 值 |
|---|---|
| 目录 | `runs/dev_full_v5/DEV/{A,B}/` |
| 记录数 | 32 = 16 DEV 任务 × 2 条件（A 官方输出反馈 / B trace-first），无遗漏无重复 |
| 代码提交 | `de5b037`（`fix(runtime): move to final-answer turn when tool attempt budget is exhausted`） |
| 模型 | `Qwen/Qwen3.5-4B` @ `851bf6e`，BF16，贪心解码，`enable_thinking=False` |
| 课程配置 hash | `configs/course/runtime_settings.json` = `faa7992…`（每条 `episode.json` 的 `config_sha256`） |
| 上游评测代码 | `third_party/code-act` @ `d607f56` |
| 作业 | 14129030（A，11 分 48 秒）、14129031（B，9 分 27 秒），`i64m1tga40u` 分区，各 1×A40，**原始 Slurm 日志随批入库**（`runs/dev_full_v5/jobs/`） |
| 逐条版本三元组 | 每份 `episode.json` 自带 `code_commit` / `model_revision` / `config_sha256` |

**为什么又跑了一遍**：v4（`runs/dev_full_v4`，`8be4109`）有一处协议偏差——工具预算（32 次尝试，含 blocked）耗尽后仍留在交互轮，直到轮次耗尽才进最终轮，与课程附件 *"Move to the final-answer turn when the tool budget is exhausted"* 不符（详见 §7）。C 在 `c/real-log-audit`（PR #3）的独立验收判定该槽位 FAIL 并定死口径后，`de5b037` 落地修复并重跑全批为 v5。**v5 与 v4 的 32 个最终答案逐条完全相同（0 处差异）**，说明修复只改变该槽位的转换路径，不改变任何行为结果。v4 保留作旧版证据，不再用于分析。

## 2. 结果概览（仅结构 + 离线正确性，不含方法结论）

| 条件 | 记录 | 有最终答案 | 无答案 | 工具执行 | 工具被拦 | 模型调用 | 生成 token | 中位耗时 | 正确数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 16 | 16 | 0 | 152 | 0 | 137 | 14759 | 30.0 s | 10/16 (62.5%) |
| B | 16 | 15 | 1 | 102 | 1 | 114 | 12887 | 27.1 s | 13/16 (81.3%) |

- 唯一无答案是 B 的 `web_browsing/price_of_legendary_potion`（`no_answer_after_turns_exhausted`），按课程规则保留、进分母。
- 终止原因：`answer`×22、`final_answer_after_turns_exhausted`×6、`final_answer_after_tool_budget_exhausted`×1（A `multi_city_business_trip`，32 次尝试用尽后立即进 final-only 轮并作答）、`final_answer_after_tokens_exhausted`×2、`no_answer_after_turns_exhausted`×1。
- 正确性来自 C 的 `scripts/score.py` + `references/offline_reference_v1.json`，输出 `runs/dev_full_v5/scored.jsonl`（`success` 与 `scoring_reason`）。
- **工具覆盖备注（按 C 的要求如实标注）**：`string_length` 工具在 v5 全部真实轨迹中**调用了 0 次**（`message_decoder/multi_step_decoding_challenge` 实际只调用了 `reverse_string` 等），即 CPU 签名测试之外的**真实数据覆盖缺口仍在**；任务 180s 截止同样 **0 次真实触发**（最长 122.2s）。

## 3. 180 秒与预算的可核对字段

`episode.json`：`task_started_at` / `task_deadline_at` / `task_seconds_limit` / `generation_stopped_at` / `generation_stopped_task_seconds` / `last_generation_finish_reason` / `episode_written_at` / `episode_written_task_seconds` / `post_generation_seconds` / `deadline_overrun_seconds` / `deadline_exceeded`。
`turns.jsonl`：每轮 `generation_seconds` / `finish_reason` / `cut_by_deadline` / `generation_stopped_at` / `generation_stopped_task_seconds`。

这批的读数：最大 `wall_seconds` = 122.2 s，最大 `generation_stopped_task_seconds` = 122.2 s，`deadline_exceeded` = 0，最大落盘延迟 `post_generation_seconds` = 0.009 s。**没有任何一次生成跨过 180 s**，所以截止截断分支在这一批里没有被真实触发（CPU 回归 `test_generate_receives_task_deadline` 与 `DeadlineBackend` 用例覆盖其语义）。

## 4. 自检命令（都能在本机跑，无 GPU）

```bash
# 结构 + 版本三元组 + 逐轮字段（C 的审计）
python scripts/audit_results.py --episodes runs/dev_full_v5/index.jsonl \
  --split DEV --conditions A B --out runs/dev_full_v5/audit.json \
  --expected-code-commit $(git rev-parse HEAD) \
  --expected-model-revision 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a \
  --expected-config-sha faa79929e12987fd301e07cb81d61e4b6ac4b87d4afce32de9b71229997dfdd1

# 统计表（有答案/无答案、blocked、中位耗时、逐任务 A/B）
python scripts/run_stats.py --runs runs/dev_full_v5/DEV

# 工具预算会计（按课程语义：blocked 不算执行）
python scripts/check_budget_accounting.py --runs runs/dev_full_v5/DEV

# 离线评分（需要 references/offline_reference_v1.json，见 docs/A_reference_export.md）
python scripts/score.py --episodes runs/dev_full_v5/index.jsonl \
  --references references/offline_reference_v1.json --out runs/dev_full_v5/scored.jsonl
```

## 5. 审计现状：C 口径下 PASS（0 error / 0 warning）

v4 曾有 2 个 error，全部集中在 `travel_itinerary_planning/multi_city_business_trip`，根因是审计脚本把 `blocked` 计入上限。C 已在 `c/real-log-audit`（PR #3）修正口径（工具预算 = 调用尝试次数，含 blocked；blocked 不执行、计入上限），并新增 `interaction_after_tool_budget_exhausted` 审计项。

v5 用 C 修正后的 `audit_results.py`（PR #3 分支，含期望版本三元组）审计：**PASS，expected=32 recorded=32，0 error / 0 warning**，无 `interaction_after_tool_budget_exhausted`。`check_budget_accounting.py`（blocked 不算执行口径）同样 PASS：254 次执行 / 1 次拦截，每轮执行 ≤ 4，每任务执行 ≤ 32。

## 6. 边界

- 只有 DEV，没有 EVAL；EVAL 必须等 B 的冻结包，本批不构成任何方法优劣结论。
- 硬件是 A40（`i64m1tga40u` 分区），与首轮 86 条基线、v4 同型号；贪心解码保证可复现，v5 与 v4 的 32 个最终答案逐条一致即为证据。
- 单任务最多 32 次工具调用；v5 里 A 条件仅 `multi_city_business_trip` 1 个任务用满预算（按修复后的协议立即进最终轮），B 条件 1 次拦截。`string_length` 真实调用 0 次、180s 截止 0 次触发，均如实标注为未覆盖。

## 7. 协议偏差：已修复（原 v4 遗留项）

课程附件原文：*"Do not execute calls beyond the limit; retain earlier effects. **Move to the final-answer turn when the tool budget is exhausted.**"*

**状态：已修复并验收**。v4 的偏差是第 32 次工具调用执行完后不切最终轮，继续留在交互轮拦截后续调用，直到轮次耗尽才进最终轮（A `multi_city_business_trip`：多走 4 轮、16 次调用全部 blocked、532 个多余输出 token）。C 的独立验收（`docs/C_DEV_V4_REVIEW_20261125.md`）判定该槽位 FAIL，并定死口径：工具预算 = 调用尝试次数（含 blocked），当前动作块执行与反馈落盘后，下一次模型调用进入 final-only；硬时间/上下文截止仍优先。

修复（`de5b037`，2026-11-25）：

- `src/runtime/runner.py`：动作块完成、反馈落盘后，检查 observer 的累计 `task_attempts`（含 blocked）是否达到 `tool_attempts_per_task`，达到即 break 进预留的 final-only 轮；硬截止优先；最终轮禁工具；同块内超限 blocked 保留为合法证据。
- 终止原因词表新增 `final_answer_after_tool_budget_exhausted` / `no_answer_after_tool_budget_exhausted`（`docs/log_fields.md` §6 同步）。
- 测试：新增 4 条 CPU 回归（32 次尝试后下一轮 final-only、blocked 计入预算、硬截止优先、转换前后变量保留），A 侧 `unittest` 107 项通过；C 另加 2 条独立集成回归（`tests/test_tool_budget_handoff.py`），合并后全套 138 项通过；C 的核验结论见 `docs/C_TOOL_BUDGET_FIX_REVIEW_20261125.md`。
- 真实证据：v5 的 A `multi_city_business_trip` 32 次尝试用尽后立即进最终轮并作答（`termination_reason=final_answer_after_tool_budget_exhausted`，最终轮 128 token、0 工具事件；答案 `0`，与 v4 相同，仍判错）；v5 与 v4 的 32 个最终答案逐条相同；C 的 v5 审计 PASS（0 error）。
