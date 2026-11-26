# C 独立验收 DEV v5（2026-11-26）

结论：本批 DEV A/B 的 C 记录审计与独立离线评分通过，可作为当前修复协议下的 DEV 基线。不是正式 EVAL，也不替代 B 方法选择及冻结。

数据提交：0f14010。全部记录的运行代码：de5b03770b093f1654589b48f17f56d35c0d4ee3；上游 d607f56c9cfe9e8632ebaf65dcaf2b4b7fe1c6f8；模型版本 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a。32 manifests 的完整配置指纹一致：b6e82b87da6d47914e353f01474ab53876882709ea7ccbb0ca08c2917949cda3。记录 config_sha256 仍是课程 runtime_settings hash，不将它称为完整运行配置 hash。

## 独立结果

| 条件 | 任务数 | 成功数 | 成功率 | 平均输入 token | 平均输出 token | 平均模型调用 |
|---|---:|---:|---:|---:|---:|---:|
| A | 16 | 10 | 62.5% | 12770.9375 | 922.4375 | 8.5625 |
| B | 16 | 13 | 81.25% | 12135.75 | 805.4375 | 7.125 |

C 重跑 audit_results：PASS，32/32 唯一槽位，0 error / 0 warning；使用本地忽略的离线参考重跑 score，32 条 success/failure_reason 与交付评分全部一致；绑定后的 summarize 为 COMPLETE。原始数据未改写。原始作业日志已包含 jobs/run-14129030.{out,err} 和 run-14129031.{out,err}，两个 out 均到达第 16 个任务；日志中存在 causal_conv1d 参考实现回退提示，不能把贪心解码或本次答案相同当成跨环境可复现保证。

共 251 次模型调用，254 次工具执行、1 次 blocked。原 v4 问题任务 A / travel_itinerary_planning/multi_city_business_trip 现在累计 32 次尝试后，第 9 次调用即 final-only，termination=final_answer_after_tool_budget_exhausted。10 个真实最终轮均无工具事件，token 限额检查通过。最大 wall_seconds=122.164，未触发真实 180 秒截止；string_length 仍为 0 次真实调用。这两项继续标未覆盖，CPU 回归不能替代真实路径证据，也不为触发路径重跑到满意。

全套 CPU 测试 138 项通过（7.117s）。此前本机 IPython history 清理警告仍属环境问题，测试结果以 Ran/OK 和退出码为准。check_run_records、check_budget_accounting 和 config_fingerprint 均通过。v4 的 INCOMPLETE 结论保持不变。

## 产物与复查

公开证据：docs/evidence/dev_v5_20261126/ 下 audit.json、condition_summary.csv、verification.json，不含离线参考答案文本。完整本地派生产物在 results/dev_v5_c_review/，包括逐任务评分、汇总、两类 PNG/PDF 图及测试日志。正式结果章节不填入本批 DEV 数字。

复查命令（仓库根目录）：

```powershell
python scripts/audit_results.py --episodes runs/dev_full_v5/index.jsonl --split DEV --conditions A B --out results/dev_v5_c_review/audit.json --expected-code-commit de5b03770b093f1654589b48f17f56d35c0d4ee3 --expected-model-revision 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a --expected-config-sha faa79929e12987fd301e07cb81d61e4b6ac4b87d4afce32de9b71229997dfdd1
python scripts/score.py --episodes runs/dev_full_v5/index.jsonl --references references/offline_reference_v1.json --out results/dev_v5_c_review/scored.jsonl
python scripts/summarize.py --scored results/dev_v5_c_review/scored.jsonl --audit results/dev_v5_c_review/audit.json --split DEV --conditions A B --out-dir results/dev_v5_c_review
python -m unittest discover -s tests
```

下一步：B 提交方法实现、DEV 候选比较与冻结配置/准确启动命令，C 按 C_EVAL_EXECUTION.md 核验后安排正式四条件 EVAL。此次不启动 EVAL、不发送队友消息、不合并 PR。
