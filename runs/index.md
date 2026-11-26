# Run Index

*每个 run 目录是什么、由谁产出、能不能当基线。*

## 1. 批次表

| 目录 | 记录数 | 产出作业 | 代码 commit | 用途 | 能否当基线 |
|---|---:|---|---|---|---|
| `runs/dev_full_v5/` | 32（16 任务 × A/B） | 14129030（A，11m48s）/ 14129031（B，9m27s），`i64m1tga40u` 1×A40，原始 Slurm 日志随批入库（`jobs/`） | `de5b037` | **当前基线**：v4 全部格式 + 工具预算耗尽即进最终轮的协议修复（附件要求）；与 v4 的 32 个最终答案逐条相同 | **是** |
| `runs/dev_full_v4/` | 32（16 任务 × A/B） | 14100888（A）/ 14100889（B） | `8be4109` | 已被 v5 取代：唯一差异是 1 个槽位（A `multi_city_business_trip`）在预算耗尽后仍滞留交互轮 4 轮（协议偏差，`A_dev_baseline_handoff.md` §7）；其余 31 槽与 v5 行为一致 | 否，仅证据 |
| `runs/dev_full_v3/` | 32（16 任务 × A/B） | 14100661 / 14100662（A）、14100663（B）、14100854（B 单槽补跑） | `c7145fa` | 已被 v4 取代：turn 字段名（`raw_text`/`tool_events`）与 0 起 `turn_index` 不被审计读取器接受；32 个答案与 v4 逐条相同 | 否，仅证据 |
| `runs/dev_baselines/` | 33（16×2 + pilot 1） | 14062955 / 14062956 | `8c1f481` | 首轮基线；提示签名错误（`find_flights` 少一参、`reverse_string/string_length` 参数名错） | 否，仅诊断 |
| `runs/dev_baselines/DEV/A/pilot_14051965/` | 1 | 14051965 | — | 1.3 tok/s 时代的 pilot；它的 `task_timeout` 是缺 FLA 内核的产物，不是协议结果 | 否 |
| `runs/eval_baselines/` | 54（27×2） | 14062957 / 14062958 | `8c1f481` | 首轮 EVAL，同上；正式 EVAL 由 C 在冻结包后跑，本批不进任何表 | 否，仅诊断 |
| `runs/dev_fix_check/` | 4（2 任务 × A/B） | 14086329 / 14086330、14089396 / 14089397 | `d6e69a4` | v1 修复验证：签名已对，但 180s 还拦不住生成（trade 跑到 236.5s / 255.3s） | 否，修复前证据 |
| `runs/dev_fix_check_v2/` | 2（1 任务 × A/B） | 14093189 / 14093190 | `7af057d` | v2 修复验证：180s 截断 + 预留最终轮 | 否，样例 |
| `runs/smoke/` | 1 | 14051595 | — | 环境冒烟输出 | 否 |

（原 `runs/repro_check/` 行已删除：作业 14072303 的记录未保留在本地与服务器，索引不应指向不存在的数据。）

## 2. 基线怎么用

- 槽位索引：`runs/dev_full_v5/index.jsonl`（32 行，只指向 `episode.json`）。`runs/dev_full_v3`、`runs/dev_full_v4` 的 index 是旧批次，勿混用。
- 逐任务评分：`runs/dev_full_v5/scored.jsonl`（C 的 `scripts/score.py` 产出）。**注意**：`score.py` 的目录模式会把 `manifest.json` 也当 episode（manifest 含 `task_id`/`condition`），必须传 `*.jsonl` 索引，否则条数翻倍。
- 汇总：`python scripts/run_stats.py --runs runs/dev_full_v5/DEV`（只读 episode.json，`pilot_*` 自动跳过）。
- 审计：`runs/dev_full_v5/audit.json`（C 修正口径后的 `audit_results.py`，PR #3 分支，含期望版本三元组）→ **PASS，0 error / 0 warning**，无 `interaction_after_tool_budget_exhausted`。
- 自洽性：`python scripts/check_run_records.py runs/dev_full_v5`（三件套齐全、`model_calls` 与 turns 行数一致、token 对得上、轮次连续）→ PASS。
- 隔离：`python scripts/check_answer_isolation.py --runs runs/dev_full_v5`（记录里不出现参考答案痕迹）→ PASS。

## 3. 记录格式（每个 episode 目录）

- `episode.json` — 结论：status、termination reason、final answer、model calls、token、工具执行/拦截、wall seconds、时间戳（`fc67310` 起）。
- `manifest.json` — 指纹：`team_commit`、`upstream_commit`、模型 revision、课程文件 hash、limits、stop_text、started_at。
- `turns.jsonl` — 每次模型调用一行：实际 messages、生成设置、原始文本、解析结果、工具事件（7 字段）、Python 输出、模型可见反馈、token、耗时、预算快照。
- `jobs/`（v5 起）— 产出该批的原始 Slurm 作业日志（`run-<jobid>.out` / `.err`），随批入库。

字段级说明见 `docs/log_fields.md`。

## 4. 读法

- A/B 对照：`runs/dev_full_v5/DEV/A/*<task>*` vs `DEV/B/*<task>*`，逐轮 diff `feedback`。
- 失败归因：`docs/failure_taxonomy.md`（首轮口径）+ `runs/dev_full_v5/stats.md`。
- 环境溯源：读任一 `manifest.json`，与 `configs/versions.json`、`docs/env_and_config.md` 对照。
