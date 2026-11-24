# 完整 DEV 基线（32 槽位，v3）

> **已被 `runs/dev_full_v4` 取代，正式基线见 `docs/A_dev_baseline_handoff.md`（数据在 `runs/dev_full_v4/`）。**
> 原因：本批 31 个槽位的 `team_commit` 是 `c7145fa`（服务器当时 HEAD 被数据提交拉过去了），单槽补跑的那条是 `7af057d`，`config_fingerprint` 因此出现 2 个值，属混合 commit；v4 在 `8be4109` 单批跑完，字段名直接对齐 C 的 reader。两批逐槽位结果完全一致（32/32），本文件保留作**复现性证据**与批次污染案例。

> 批次：`runs/dev_full_v3`｜代码 commit：`c7145fa`（31 条）/ `7af057d`（1 条补跑，见 §6）｜协议：课程附件（180s / 12 轮 / 3072 token / 32 次工具）
> 本文只报事实与可复核路径，正确性由 C 用 `scored.jsonl` 复核；A/B 差异的解释归 B/C。

## 1. 批次定义

| 项 | 值 |
|---|---|
| 目录 | `runs/dev_full_v3/DEV/{A,B}/` |
| 槽位 | 16 个 DEV 任务 × A/B = **32 个唯一槽位**，无 pilot、无旧批次、无重复 run_id |
| 作业 | `14100661`（A 前 8 题）、`14100662`（A 后 8 题）、`14100663`（B 全 16 题）、`14100854`（B 单槽补跑） |
| 日志 | `runs/dev_full_v3/jobs/run-<job>.{out,err}`（从集群 `~/codeact-work/logs/` 原样取回） |
| 索引 | `runs/dev_full_v3/index.jsonl`（32 行，指向 `episode.json`） |
| 配置指纹 | `python scripts/config_fingerprint.py runs/dev_full_v3/DEV` → 见 §5 |
| GPU | 1 卡 / 作业；`i64m1tga40u` / `i64m1tga800u` 分区，实际节点报 NVIDIA A40 49 GB |

## 2. 结果概览（只读 episode.json）

| 条件 | 记录 | 有最终答案 | 无答案 | 模型调用 | 输入 token | 生成 token | 工具执行 | 工具拦截 | 中位耗时 | 最长 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 16 | **16** | 0 | 141 | 217 507 | 15 291 | 152 | 16 | 30.4 s | 121.4 s |
| B | 16 | **15** | 1 | 114 | 194 172 | 12 887 | 102 | 1 | 27.3 s | 123.5 s |

终止原因（A / B）：

| `termination_reason` | A | B |
|---|---:|---:|
| `answer`（交互轮直接答） | 9 | 13 |
| `final_answer_after_turns_exhausted` | 6 | 1 |
| `final_answer_after_tokens_exhausted` | 1 | 1 |
| `no_answer_after_turns_exhausted` | 0 | 1 |
| `task_timeout` | 0 | 0 |

- 最终回答轮实际触发：A 7 次、B 3 次（`generation_settings.is_final_turn=true`）。
- **无答案 1 条**：B `web_browsing/price_of_legendary_potion`（13 次调用、12 次工具，轮次用尽后最终轮没写出可解析答案）——预算语义的正常出口，判 0 分，不是故障。
- **超时 0 条**：本批最长 123.5 s，没有走到 180 s 截止，因此"到点截断"仍只有 CPU 回归为证（见 `docs/protocol_verification.md`）。
- 工具拦截 16 次集中在 A 的 `travel_itinerary_planning/multi_city_business_trip`（48 次尝试：32 执行 + 16 超过任务 32 次上限）；B 只有 1 次。

## 3. 逐任务评分（C 的 `scripts/score.py`）

数据：`runs/dev_full_v3/scored.jsonl`（`--episodes runs/dev_full_v3/index.jsonl --references <离线参考>`）。

| 任务 | A | B |
|---|:--:|:--:|
| message_decoder/maximum_value_decoding | ✓ | ✓ |
| message_decoder/multi_step_decoding_challenge | ✗ | ✗ |
| message_decoder/specific_decoded_character | ✗ | ✓ |
| trade_calculator/bulk_trade_quantity_discount | ✓ | ✓ |
| trade_calculator/interstellar_trade_transaction | ✓ | ✓ |
| trade_calculator/optimizing_bulk_purchase_discounts | ✗ | ✗ |
| travel_itinerary_planning/adventure_trip | ✗ | ✓ |
| travel_itinerary_planning/cheapest_new_york_trip | ✓ | ✓ |
| travel_itinerary_planning/multi_city_business_trip | ✗ | ✓ |
| travel_itinerary_planning/new_york_trip_with_specific_preferences | ✗ | ✓ |
| web_browsing/email_of_allison_hill | ✓ | ✓ |
| web_browsing/expertise_of_allison_hill | ✓ | ✓ |
| web_browsing/people_in_sales | ✓ | ✓ |
| web_browsing/price_of_legendary_potion | ✓ | ✗（无答案） |
| web_browsing/price_of_legendary_wand | ✓ | ✓ |
| web_browsing/total_price_of_selected_items_0 | ✓ | ✓ |
| **合计** | **10/16** | **13/16** |

- A 的失败：`multi_step`（字符串）、`specific_decoded`（字符串）、`optimizing_bulk`（数值）、`adventure`（数值）、`multi_city`（数值，答 0，撞 32 次工具上限）、`new_york_specific`（数值）。
- B 的失败：`multi_step`（与 A 同答 `PbVdqwzru`）、`optimizing_bulk`（与 A 同为错值）、`price_of_legendary_potion`（无答案）。
- 同一任务 A/B 同题不同答的例子（可直接做配对案例）：`specific_decoded_character`（A `gowtwvpkmBjmE` / B `rzhehgavxMuxP`，B 对）、`multi_city_business_trip`（A `0` / B `1050`，B 对）、`new_york_trip_with_specific_preferences`（A `165` / B `615`，B 对）、`adventure_trip`（A `1690` / B `2200`，B 对）。

## 4. 完整性核验

| 检查 | 命令 | 结果 |
|---|---|---|
| 槽位齐全无重复 | `python scripts/make_run_index.py runs/dev_full_v3 --split DEV` | `PASS: 槽位齐全且无重复`（32/32） |
| 记录自洽 | `python scripts/check_run_records.py runs/dev_full_v3` | 32/32 PASS（三件套齐全、`model_calls`==turns 行数、token 对得上、轮次连续） |
| 答案隔离 | `python scripts/check_answer_isolation.py --runs runs/dev_full_v3` | PASS（记录中无 `expected_output` 等痕迹） |
| 配置统一 | `python scripts/config_fingerprint.py runs/dev_full_v3/DEV` | **不通过**：2 个 fingerprint（31 条 `c7145fa`、1 条补跑 `7af057d`），正是本批不能当正式基线的原因 |

## 5. 配置指纹

```text
python scripts/config_fingerprint.py runs/dev_full_v3/DEV
ERROR: 同一批次里出现多个 fingerprint（协议不统一，不能当同一批基线）
manifests=32 distinct_fingerprints=2
 7ee8ff929e48c0e4ff527c5e774ab6bd73a11e76fc1de81a6df8da61046de6c3  x31   # c7145fa（整批原跑）
 e4fe086ff67af7fa673189a78009ae6caca18c54db165164d7418757584d0bb9  x1    # 7af057d（单槽补跑）
```

差异字段是 `team_commit`：整批投在 `c7145fa`（服务器当时 HEAD 被一次数据提交拉过去了，`runtime` 代码与 `7af057d` 相同），补跑那条来自 `7af057d` 独立工作树。结果与 v4 逐槽位相同，但**批次口径上不属于同一份代码**，故 v4 重跑。指纹覆盖协议相关字段：课程 hash + 团队/上游 commit + 模型 revision + 解码设置 + limits + 停止串 + backend；GPU 型号不进指纹，记在 `docs/gpu_ledger.md`。

## 6. 本批的两次补跑与原因（必须知道）

1. **B 条件的重复作业**：`14100663`（22:22:27 起）与 `14100664`（22:24:09 起）被投到**同一个 `RUNS_ROOT`**、同一批 `run_id`，会互相覆盖目录。`14100664` 在 50 s 后被 scancel。
2. **一个槽位被写坏**：`B message_decoder/maximum_value_decoding` 出现 `manifest` 来自 14100664、`episode.json` 来自 14100663、`turns.jsonl` 只有 2 行的混合状态（`check_run_records.py` 抓到的就是它）。用 `7af057d` 的独立工作树（`~/wt7af`）重跑该单题，`RUNS_ROOT=runs/dev_v3_repair`；先后投 `14100842`、`14100845`（A40 排队未启动，撤销）、`14100854`（A800 排队未启动，撤销），最终 **`14100878`（debug 分区，22:35:35–22:36:31，56 s）** 跑成，再把三件套覆盖回该槽位（6 次调用 / 6 行 turns / token 与 episode 对得上 / 答案 `987`）。
   - 该槽位的 `manifest.team_commit` 是 `7af057d`（其余 31 条为 `c7145fa`）；`started_at` 晚于本批。
   - 这不是"重跑到成功"：重跑原因是被写坏，不是答案不对；其余槽位一次跑完，未重跑。
3. 另有一条槽位（`B message_decoder/specific_decoded_character`）来自 14100664 的完整一次运行（内部自洽），与本批同协议同 commit，保留并在 `docs/gpu_ledger.md` 标注。

## 7. 与首轮数据的关系（不要混用）

首轮 `runs/dev_baselines`（`8c1f481`）的提示签名是错的（`find_flights(destination, date)`、`reverse_string(string)`），它的工具 TypeError 与失败分布不能与本文并列。本批是修复后第一次完整 DEV：

| 指标 | 首轮 A/B（诊断） | 本批 A/B |
|---|---|---|
| 有答案 | 15/16 · 14/16 | 16/16 · 15/16 |
| 工具 TypeError | 218 次事件 | 0（见 §8） |
| 超时 | 0 | 0 |

## 8. 签名修复的实际效果（真实调用证据）

- `reverse_string` / `string_length`：提示里是 `s: str`；三个 message_decoder 任务共 34 次调用、错误 0（首轮同任务必然 `unexpected keyword argument`）。
- `find_flights`：`cheapest_new_york_trip` 4 次调用全部 `ok`，答案 `615`（与 v1/v2 样例一致）。
