# C 复核：工具尝试预算修复（2026-11-25）

结论：A 的 `de5b03770b093f1654589b48f17f56d35c0d4ee3` 通过本次代码与 CPU 复核，可以使用该固定运行版本开始新版完整 DEV A/B。这个结论不代表尚未产生的 v5 数据已通过验收。

## 已核验

- runner 使用累计 `observer.task_attempts`，包括 blocked；当前代码块执行和反馈记录完成后，下一次模型调用转为 final-only。
- 最终轮最多 128 token，不执行其中的 Action；首个可解析 Answer 结束。
- 时间截止检查优先于工具预算转换；A 的 deadline 回归覆盖预算同时耗尽时不再调用模型。上下文由 `Budget.allocate` 限制，剩余上下文为零时不生成；本次未新增 GPU 上下文或 deadline 实验。
- A 的四项新增 CPU 回归覆盖转换、blocked、deadline 优先级与此前执行效果。
- C 另加 `tests/test_tool_budget_handoff.py` 两项集成回归：单块 32 次尝试只有 4 次执行、28 次 blocked，第二次模型调用直接 final-only；最终轮给出 Action 也不执行。两种输出均经 C turns adapter 和工具审计复核，无问题。

## 验证结果

`python -m unittest discover -s tests -p test_tool_budget_handoff.py`：2 项通过。

`python -m unittest discover -s tests`：138 项通过（4.452s，退出码 0）。本地日志 `results/dev_v4_c_review/tests_after_de5b037.log`。测试结束存在 IPython history SQLite 只读及连接清理警告，未计为测试失败；这些 CPU 结果不充当真实模型运行证据。

## 下一步与证据边界

1. A 可按已提出的 `runs/dev_full_v5` 新目录运行固定版本的 16 DEV × A/B，共 32 个唯一槽位，保留全部失败与无答案，随批次提交原始 jobs 日志、索引和版本信息。
2. C 在数据推送后继续验收逐轮预算、32 槽位完整性、离线评分和代码/模型/配置身份。该批是否合格以数据审计结果为准。
3. v4 继续保留，其旧版本交互超额问题及 INCOMPLETE 结论不因代码修复而改变。
4. message_decoder 是否实际调用 `string_length`，以及真实生成是否触发 deadline，按新轨迹注明已覆盖或未覆盖；不能仅凭任务名称声明覆盖，也无需为触发特定路径反复重跑。
5. 这次仅放行 A/B 新版 DEV。方法冻结与正式四条件 EVAL 仍按 `docs/C_EVAL_EXECUTION.md` 的条件推进。
