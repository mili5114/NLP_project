# C 对 DEV v4 的独立验收（2026-11-25）

## 结论

**未通过完整协议验收。** 32/32 数据完整、版本一致、评分可复现、超限调用已被阻止；但 A 条件 `travel_itinerary_planning/multi_city_business_trip` 用尽任务工具预算后仍进行了 4 个交互轮，违反课程附件 §2 的最终轮转换要求。不得把结构/执行计数 PASS 写成完整协议 PASS。

这是 A 已在 `docs/A_dev_baseline_handoff.md` §7 披露的问题。C 本次补齐了之前漏掉的审计规则，不要求重复提交已交付材料。

- 核验远端快照：`5a757d4`；运行代码：`8be4109831b4e431525664e341357cd422739b96`。
- 原始目录：`runs/dev_full_v4`。全部原始记录及 A 原有审计结果保持不变。
- C 审计/评分/图表：`results/dev_v4_c_review/`（本地产物，git 忽略）。
- 可提交证据：`docs/evidence/dev_v4_20261125/`，含新审计、汇总、输入文件 SHA256 和核验回执；不含参考答案原文。

## 验收结果

| 项目 | C 核验结果 |
|---|---|
| 完整性 | 16 DEV × A/B = 32 唯一槽位，无遗漏；三件套自洽 |
| 运行身份 | 32 条均为同一 runtime commit；模型 revision 与固定版本一致 |
| 完整运行指纹 | 32 条同为 `32e36f9535f0d7a217677fc3d84699e9269a456654dc8dd48b6251da7f6228cb`；课程设置 hash 另行核对，二者不混用 |
| 工具限制 | 254 次执行、17 次 blocked；执行未超限，被拦事件无返回结果 |
| 最终轮 | 10 次真实触发；0 工具事件；输出最多 128 tokens |
| 时间 | 最大 wall 122.733s、最后生成停止 122.734s、生成后开销 0.016s；没有真实 deadline 截断 |
| 参考导出 | 本机从固定上游重新导出 43 条；内容及每条参考值 hash 全部与公开清单一致 |
| 评分复算 | 32/32 success 与 scoring_reason 均与 A 交付一致；无答案保留为失败 |
| 答案隔离扫描 | 96 份在线记录未发现扫描器检查的答案字段/标记；这不是执行环境硬隔离证明 |
| 测试 | 当前合并后的 CPU/离线测试 132 项通过；不是 GPU 推理复跑 |
| 工具耗尽后切最终轮 | **FAIL：1 个槽位，4 个违规交互轮** |

参考内容 SHA256：`683697256d7431d3253aacd58850ed0209d244cef460099714685f242b3118e4`。参考原文仅在本机忽略目录中，未入库，也未用于模型运行。本次只评分 DEV，未计算 EVAL 的结果。

## 已复算的描述性统计（INCOMPLETE，不是最终结果）

| 条件 | 正确数 | 成功率 | 每任务平均输入 tokens | 每任务平均输出 tokens | 平均模型调用数 |
|---|---:|---:|---:|---:|---:|
| A | 10/16 | 62.50% | 13594.1875 | 955.6875 | 8.8125 |
| B | 13/16 | 81.25% | 12135.7500 | 805.4375 | 7.1250 |

A 的一个任务存在额外交互轮，因此不能据此发布反馈策略的最终效率结论。不可删除该槽位、截短原轨迹或手工扣 token 来修复；修复后模型的最终回答也可能变化。汇总脚本因 audit 不完整返回退出码 2，图表保留 INCOMPLETE 标记。

## 具体协议偏差与审计修复

附件 `configs/course/Assignment_Attachment.txt` §2 明确要求工具预算耗尽后转最终回答轮。这里的预算是 **调用尝试次数**，包含 blocked 尝试；执行次数与尝试次数不能混为一谈。

受影响槽位：A / `travel_itinerary_planning/multi_city_business_trip`。

- 第 1–8 轮：共 32 次执行，到达任务尝试上限。
- 第 9–12 轮：仍按交互轮生成，每轮 133 个输出 tokens、4 个 blocked 事件。
- 第 13 轮：才进入最终回答轮；终止原因为 `final_answer_after_turns_exhausted`。
- 不该发生的 4 个交互轮共生成 **532 输出 tokens**。该任务总输出 1823 tokens、模型调用 13 次。

C 在 `audit_tool_attempts` 新增 `interaction_after_tool_budget_exhausted`：当之前轮次已耗尽任务尝试预算，后续任何非最终轮均失败，包括完全没有工具事件的交互轮。同一个代码块内的超限 blocked 事件仍合法；当前块的既有执行效果保留；若因硬时间/上下文停止而没有后续调用，不误报。

新增 6 项测试覆盖转换、空交互轮、同块 blocked、blocked 消耗任务预算、硬停止及完整审计集成。此次真实数据产生 4 项错误，全部属于上面同一个槽位；没有把正常拦截误判为超限执行。

## 覆盖边界和交接状态

- `find_flights`：v4 有 40 次 ok、8 次 blocked；`reverse_string`：12 次 ok。
- **v4 没有 `string_length` 工具事件**，不能把该函数的签名测试或 decoder 任务名等同于真实调用覆盖。A 的 CPU 签名测试已通过；原计划独立 decoder 作业 14100225/14100226 已在资源账目注明排队撤销。
- 真实 180 秒截断与上下文耗尽路径本批未触发，保留 CPU 测试和覆盖限制即可，不要求为了触发而反复跑 GPU。
- 作业号 14100888/14100889 和用时已写入资源账目，但当前 Git 快照没有 `runs/dev_full_v4/jobs/` 原始 Slurm 日志；资源记录已收到，原始调度/作业日志尚未独立对账。
- 执行环境同进程、无硬沙箱的限制按 A 原交接保留；字符串扫描通过不能证明工具函数 globals 无法触及答案。

## 给 A/B 的一次性交接

1. A 在运行时当前动作块完成、记录反馈之后，用 observer 的**累计 task_attempts** 判断任务工具预算是否耗尽；耗尽则下一次模型调用应为预留最终轮。不得只判断 executed 次数。硬时间/上下文上限仍优先停止，最终轮继续禁止工具。
2. A 加 CPU 回归：第 32 次尝试后下一轮 final-only；此前的 blocked 尝试也消耗任务预算；保留前序执行效果；硬截止不额外调用模型。
3. 先交修复提交与测试结果，C 复核后再用新版本在新目录跑完整 DEV A/B 32 条，保持一致版本，不为答案正确性重试；保留 v4。原始作业日志可随下一批一并交付，无需重复写已有环境/参考导出说明。
4. B 在课程运行协议修复后完成候选选择和冻结。C/D 应复用同一修复后的运行时；若已有旧协议候选数据，需明确其诊断身份，不能混入冻结比较。
5. C 重新执行审计、评分、汇总；通过后再推进冻结的四条件正式 EVAL。

## 本机复现命令（仓库根目录）

```powershell
python -m unittest discover -s tests
python scripts/export_references.py --out references/offline_reference_v1.json --no-manifest
python scripts/config_fingerprint.py runs/dev_full_v4/DEV
python scripts/check_run_records.py runs/dev_full_v4
python scripts/check_budget_accounting.py --runs runs/dev_full_v4/DEV
python scripts/check_answer_isolation.py --runs runs/dev_full_v4
python scripts/audit_results.py --episodes runs/dev_full_v4/index.jsonl --split DEV --conditions A B --out results/dev_v4_c_review/audit.json --expected-code-commit 8be4109831b4e431525664e341357cd422739b96 --expected-model-revision 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a --expected-config-sha faa79929e12987fd301e07cb81d61e4b6ac4b87d4afce32de9b71229997dfdd1
python scripts/score.py --episodes runs/dev_full_v4/index.jsonl --references references/offline_reference_v1.json --out results/dev_v4_c_review/scored.jsonl
python scripts/summarize.py --scored results/dev_v4_c_review/scored.jsonl --audit results/dev_v4_c_review/audit.json --split DEV --conditions A B --out-dir results/dev_v4_c_review
python scripts/plot_results.py --summary results/dev_v4_c_review/summary.json --out-dir results/dev_v4_c_review/plots
```

参考导出命令首次执行使用；文件已存在时先核对内容 hash，不覆盖原文件。audit 当前应退出 1，summarize 应退出 2；这是识别已知协议偏差后的预期结果。不要用当前 HEAD 当运行期 expected-code-commit：数据记录的实际运行版本是上面固定的 `8be4109…`。
