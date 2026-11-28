# C 验收：4 条修复验证样例

输入 main `816fb14`；目录 `runs/dev_fix_check/DEV/`。这是2个 DEV 任务×A/B 的工程健康检查，不是完整16题×A/B，不是正式冻结后 EVAL。没有使用离线参考答案，也没有正确率结论。

## 已完成

- 同步 A 新交付，保留旧诊断数据独立目录。
- 新增明确的 DEV 子集选择 `configs/evaluation/dev_fix_check_tasks.json`，只选择课程名单内任务。脚本报告 expected=4、official_DEV_expected=32、full_DEV_covered=false，避免把子集冒充全量。
- 四条 episode/manifest/turns 均可适配，逐轮 tokens、调用数、答案出口及工具事件计数通过有限结构检查。
- 总计7次工具尝试，全部实际执行，无 blocked。4条记录不丢弃，超时同样保留。
- C 测试79项通过（此次新增3项：子集状态、非法子集拒绝、超时保留与标记）。

复现命令（必须用尚不存在的新输出目录）：

```powershell
python scripts/prepare_runtime_records.py --source runs/dev_fix_check/DEV --tasks configs/evaluation/dev_fix_check_tasks.json --out-dir results/dev_fix_check_review
```

本批输入返回1，因为2条 wall overrun 待检查；不是全量正式审计 PASS。

## 修复验证范围

| 任务 | A 耗时 | B 耗时 | 有证据支持的结论 |
|---|---:|---:|---|
| travel_itinerary_planning/cheapest_new_york_trip | 17.427s | 78.458s | 提示包含正确三参数 find_flights；实际代码也用三参数调用；两条件均完成并产生答案。未评分正确性。 |
| trade_calculator/optimizing_bulk_purchase_discounts | 236.537s | 255.261s | 均在4次模型调用后 task_timeout，无答案、没有最终轮，尚未触发到预留最终轮验证点。 |

该子集没有 message_decoder 任务，因此不能证明 reverse_string/string_length 的修正已在真实数据中被验证；相应源码修复仍可单独审阅。

## 需要 A 确认的两个问题

### 1. 在途模型生成跨过180秒边界

课程规定 task_seconds=180。本次超时样例的日志可重建：

- A 最后一轮 budget.elapsed_seconds=236.543、该轮elapsed_seconds=76.694817，估算本轮开始约159.848s，剩余约20s，但调用一直持续到约237s。
- B 最后一轮 budget.elapsed_seconds=255.266、该轮elapsed_seconds=82.934897，估算开始约172.331s，剩余约8s，但调用持续到约255s。

两次调用均不是已超过180秒后再启动，而是一次在途生成跨越截止点。这也说明wall超时不能仅凭数字就说“时间耗尽后还新发起调用”。但结合长时间差与backend.generate未接收剩余deadline的当前接口，需核对180秒硬限制是否真正作用于在途生成。

A 应在其模型/runner模块处理实际deadline，将可验证的时钟与剩余时间写入日志，说明取消/同步开销；C 不通过改阈值或删样本把问题隐藏。不能为验证最终轮而放宽正式180秒预算。最终轮逻辑可先用 FakeBackend CPU 回归验证，再在正常运行的DEV里取得真实触发证据，避免按正确率重跑。

### 2. manifest 声明的团队代码提交目前不可追溯

4份 manifest 均声明 team_commit=`d6e69a4d9377e05a1d761ef0a3e7aae28e9cc5b2`。本地fetch后找不到此对象，GitHub commits API也返回422（No commit found for SHA）。这不证明代码内容错误，但目前无法从该SHA复现对应源码。

请 A 推送/保留实际运行的原提交（如存在），或提供可验证源码快照及其与已公开修复提交的差异、未提交修改状态；不应为让检查通过而直接改写旧manifest的真实版本记录。新实验记录使用可访问的源码身份。

## 下一步

1. A 处理时间边界与源码身份，提供实际运行证据；需要验证字符串工具时选一个DEV message_decoder样例。
2. 完整DEV仍待同一协议版本的32条基线，不能用本批4条覆盖旧数据后混成完整基线。
3. 参考答案导出及B的候选/冻结仍待交接。C可继续完善离线工具与报告结构，不凭任务文字编造标准答案，不读取早期EVAL来调方法。
