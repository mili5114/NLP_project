# C 后续核验：A 已修代码，待新运行证据

日期：2026-11-24。检查远程 main 提交 `beacbfc`，与首轮日志提交 `95ce5b0` 区分。

## A 的修改已存在

- `src/runtime/tasks.py` 新增 `_apply_course_signatures`，在加载任务时改写 find_flights/reverse_string/string_length 的提示签名，并与真实函数参数核对，不改 third_party。
- `src/runtime/runner.py` 的交互 `alloc.max_new_tokens <= 0` 分支不再直接设置 token_budget_exhausted，而进入最终轮处理；最终轮请求前检查任务时间。
- `docs/failure_taxonomy.md` 已撤回“天然签名陷阱”的解释；首轮数据保留为诊断材料，不进入冻结后正式比较，等待修复版一致基线。
- A 增加了对应 CPU 回归测试。代码审阅不等于新 GPU 数据验证。

截至本次 fetch，`beacbfc` 没有新增或替换 runs 下的数据，日志仍来自旧版本。因此再次读取旧日志仍发现旧签名/最终轮问题是预期现象，不能说修复无效，也不能说新实验已通过。

## C 本轮完成

新增 `src/evaluation/tool_audit.py` 并接入现有 auditor 与真实 DEV preparation：

1. 每个事件都计为一次调用尝试，blocked 也消耗尝试计数；每个 Action 重置块内序号，任务计数跨 Action 累积。
2. ok/error 都计入实际执行，blocked 不计入执行。尝试超过4/32时应有 blocked 记录，而不是因记录数超限直接报错。
3. 检测超限却执行、未到限制却拦截、事件序号错误、未知状态、blocked 仍含返回值。
4. 对照 episode 的 executed/blocked 与逐事件计数，拒绝缺失、负数、布尔和不一致计数。

这修复的是 **C 自己的审计误报**，不更改 A 的事件或运行器。

新增测试覆盖合法第五次拦截、32次后的拦截、blocked 消耗任务尝试、error 算执行、过早拦截、非法事件、计数不一致等。C 测试总数 **76 项，全部通过**（不含 A 的运行器测试）。

## 真实 DEV 再检查

命令（输出必须是新目录）：

```powershell
python scripts/prepare_runtime_records.py --out-dir results/dev_adapter_review_20261124
```

旧版32条 DEV 中共有 **282 次尝试 = 276 次实际执行（含工具异常）+ 6 次 blocked**。事件顺序、已记录的拦截语义和 episode 工具计数一致；该有限事件检查没有新增工具拦截问题。32/32槽位齐全，排除旧 pilot。

整体 preparation 仍返回1，因为输入仍是旧版诊断数据：8条 find_flights 旧提示、6条 reverse_string/string_length 旧参数、2条待最终轮修复的旧记录。三个工具问题的任务集有重合。不是正式审计 PASS，不计算正确率，不检查 EVAL 结果。

## 下一步交接

- A 提供一个修复版真实 DEV 三件套与 GPU 作业记录，manifest 的 team_commit 应能定位到包含修复的代码，并记录是否有未提交修改。C 对新目录检查，不能覆盖旧数据。
- 优先抽样一条 travel_itinerary_planning 验证修正签名，以及一条原来触发预算出口的 DEV 验证最终轮；这是工程健康检查，不按是否答对决定重试。
- A 提供固定上游版本的私有离线 reference 导出或导出入口；C 尚未编造参考答案或评分。
- B 仍需按 DEV 完成候选与冻结交接。C 不使用早期 EVAL 结果帮助 B 调参。
- 完整冻结 hash、tokenizer/模型 provenance、硬时间/上下文与参考答案隔离尚未全部认证。blocked 审计只能验证已记录事件，不能证明没有未记录调用或副作用。
