# 阶段一：v2 修复验证简报（A）

> 给 C 核验用。只写可核对的事实与路径，不重复整理已有材料。
> 时间：2026-11-24 22:40。协议字段见 `docs/log_fields.md`，环境见 `docs/env_and_config.md`。

## 1. 一句话结论

v2（`7af057d`）修好了两件事：**工具签名与真实函数一致**、**预留的最终回答轮不再被绕开**；
**180s 到点截断**这条分支仍无真实样例（两集都在 141s 内正常结束），只有 CPU 回归为证。
v3 的 message_decoder 真实样例作业在排队阶段被撤，改由完整 DEV 批次的 `message_decoder/multi_step_decoding_challenge` 覆盖。

## 2. 提交号与数据目录

| 项 | 值 |
|---|---|
| 运行代码（`manifest.team_commit`） | `7af057d46c091181a363fac7ff055efc5fc297d5`（v1 样例为 `d6e69a4`） |
| 上游代码 | `d607f56c9cfe9e8632ebaf65dcaf2b4b7fe1c6f8` |
| v1 数据提交（保留，不覆盖） | `731efab` → `runs/dev_fix_check/`（travel A/B + trade A/B） |
| v2 数据提交 | `21adc7a` → `runs/dev_fix_check_v2/`（trade A/B） |
| 配置 fingerprint | v2：`e4fe086f…0bb9`（`python scripts/config_fingerprint.py runs/dev_fix_check_v2/DEV`） |

## 3. 作业号与日志

| 作业 | 名称 | 用途 | 状态 | 日志 |
|---|---|---|---|---|
| 14086329 / 14086330 | `fixchk-A/B` | v1：`cheapest_new_york_trip` 验签名 | COMPLETED（57s / 7m49s） | `~/codeact-work/logs/run-14086329.{out,err}` |
| 14089396 / 14089397 | `fixchk2-A/B` | v1：`optimizing_bulk_purchase_discounts` 验最终轮 | COMPLETED（9m22s / 10m19s） | `logs/run-14089396.*`、`run-14089397.*` |
| 14093189 / 14093190 | `v2chk-A/B` | v2：同两个任务，验 180s + 最终轮 | COMPLETED（3m36s / 3m39s） | `logs/run-14093189.*`、`run-14093190.*` |
| 14100225 / 14100226 | `fixchk3-A/B` | v3：`message_decoder/multi_step_decoding_challenge` 验 `s` 参数 | **CANCELLED（未启动）** | 无输出 |

每个 episode 目录都保留 `episode.json` / `turns.jsonl` / `manifest.json` 三件套，未做任何裁剪。

## 4. 逐项检查

| 检查项 | 结果 | 证据 |
|---|---|---|
| 180s 任务截止（生成中途截断） | **真实样例未覆盖**；CPU 回归通过 | v2 A 124.4s / B 140.6s 正常结束；`tests/…::test_deadline_cut_records_generation_stop_and_persist_separately`（`task_seconds` 缩到 0.2s + 慢后端，验证截断轮照常落盘、不执行动作、不进最终轮） |
| ≤185s 工程线（含停止/同步/落盘） | **通过** | v2 A `wall_seconds=124.426`、B `140.586`，均 < 185；修复前 v1 同任务为 `236.537` / `255.261`（超截止，属旧代码 `d6e69a4`，保留作对照） |
| 日志区分"生成停止"与"最终落盘" | **通过（字段自 `fc67310` 起）**；本批数据用派生口径 | v2 数据没有显式字段，按 `docs/log_fields.md` §8：生成停止 ≈ 最后一轮 `budget.elapsed_seconds`（124.436 / 140.597），落盘 ≈ `wall_seconds`（124.426 / 140.586），差值在毫秒级 |
| 最终回答轮（预留 128、禁工具、`is_final_turn`） | **通过** | v2 A/B 各 9 次调用，第 9 行 `generation_settings.is_final_turn=true`、`max_new_tokens=128`、`budget.final_turn_used=true`，`termination=final_answer_after_tokens_exhausted`，答案 `256158` / `243960` |
| 旅行任务 `find_flights` 签名（提示 + 真实调用） | **通过** | 提示：`find_flights: … Arguments: from_location (str), to_location (str), date (str)`；真实调用：`find_flights('E','B','2023-11-10')` → `ok`（v1 travel A 4 次调用得 `615`，B 78.5s 得 `615`） |
| `message_decoder` 的 `reverse_string(s)` / `string_length(s)` | 提示层**通过**（CPU）；真实调用**未覆盖** | `::test_message_decoder_s_params_fixed` 断言提示里是 `reverse_string(s: str)` 且不含 `reverse_string(string`；v3 作业被撤，真实调用证据待 `dev_full_v3` 的 `multi_step_decoding_challenge` |
| 旧记录保留、不覆盖 | **通过** | `runs/dev_fix_check/`（v1，4 集）与 `runs/dev_fix_check_v2/`（v2，2 集）并存；首轮 86 条 `runs/dev_baselines/` 未改动，仅作诊断 |

## 5. 与首轮数据的区别（避免误用）

- 首轮基线 `runs/dev_baselines/`（`team_commit=8c1f481`）用的是**错误签名**（`reverse_string(string: str)`、`find_flights(destination, date)`），只能当失败诊断材料，**不进入新基线**。
- v1 `runs/dev_fix_check/` 有正确签名，但**没有** 180s 生成中途截断，trade 任务跑穿到 237s/255s —— 保留作"修复前"证据。
- v2 `runs/dev_fix_check_v2/` 是当前唯一"两处修复都在"的真实样例，但只覆盖 1 个任务 × A/B。

## 6. 下一步（不阻塞）

完整 DEV 32 槽位（`runs/dev_full_v3`，`COND=A/B`，作业 `devfull3-A/B`）跑完后，本表两处"未覆盖"会由真实数据补上：`message_decoder/multi_step_decoding_challenge`（签名）与任一走到 180s 的任务（时间截止，若仍未出现则继续标"未覆盖"，不重跑到触发）。
