# 首轮基线失败清单分类（步骤 19 交付）

> 数据范围：86 个 episode（DEV 16×2 + EVAL 27×2），A40 作业 14062955–58（2026-11-23）。
> 记录入库于 commit `95ce5b0`。旧 pilot（1.3 tok/s 时代）**不计入**本表。
> 本文只做"失败去哪了"的归因，不评分正确性（正确性等 C 的离线 scorer，步骤 18）。

## 一、episode 终止语义分布

| 终止原因 | DEV-A | DEV-B | EVAL-A | EVAL-B | 合计 | 语义 |
|---|---|---|---|---|---|---|
| `answer`（模型主动给出答案） | 10 | 13 | 15 | 20 | 58 | 正常出口 |
| `final_answer_after_turns_exhausted`（轮次用尽后补答） | 5 | 1 | 8 | 5 | 19 | 轮次预算耗尽 |
| `token_budget_exhausted`（3072 token 用尽） | 1 | 1 | 2 | 0 | 4 | 生成预算耗尽 |
| `no_answer_after_turns_exhausted`（轮次用尽且补答仍无答案） | 0 | 1 | 2 | 2 | 5 | 轮次预算耗尽 |
| `task_timeout`（180 秒超时） | 0 | 0 | 0 | 0 | 0 | 未发生 |

最终答案率：**A 38/43，B 39/43**（DEV+EVAL 合并）。

## 二、五类失败分类（计划要求的口径）

| 类别 | 计数 | 说明 |
|---|---|---|
| 解析失败（Action 无法解析） | **0 轮** | 1728 轮中 `parsed=None` 为零；上游解析格式运行稳定 |
| 无答案 | **9 episode** | 全部为预算耗尽（4 token + 5 轮次），无一例崩溃或空转 |
| 非法参数（工具抛 TypeError） | **218 次事件** | 见第三节明细；集中在 2 个签名陷阱 |
| 超时 | **0** | 180s 上限内全部跑完（最慢 130s） |
| 预算耗尽 | **28 episode** | 轮次 24 + token 4；属预算语义正常出口，非 bug |

## 三、工具层错误明细（给 B 的方法动机）

86 episode 共 **1092 次工具调用事件**：ok 726 / error 218 / blocked 148。

| 错误类型 | 次数 | 受影响任务数 | 性质 |
|---|---|---|---|
| `find_flights() missing 1 required positional argument: 'date'` | 185 | A 12 / B 11 | **任务自身陷阱**：系统提示词写 `find_flights(destination, date)`，真实签名 3 参数（多一个必填位）。模型照提示词调用必然 TypeError |
| `book_hotel() got an unexpected keyword argument 'preference…'` | 28 | — | 同类陷阱：提示词与真实签名不一致 |
| `find_flights() got an unexpected keyword argument …` | 5 | — | 同类陷阱的变体 |

**给 B 的含义**：travel_itinerary_planning 类任务里，模型"按提示词写代码"反而必然报错。这为反馈层研究提供了天然素材——错误反馈（Python traceback）是否会教会模型从提示词签名切换到真实签名，正是 A/B 两种反馈设计要回答的问题。

## 四、预算拦截（blocked）

| 拦截类型 | A | B | 合计 |
|---|---|---|---|
| 块内 4 次上限（`per-action limit 4`） | — | — | 76 |
| 任务 32 次上限（`per-task limit 32`） | — | — | 72 |
| 合计 | 102 | 46 | **148** |

blocked 事件已按课程语义保留执行效果，只拦超额调用；episode 级 `tool_attempts_blocked` 与 turns 级事件逐条相等（已核验 86/86）。

## 五、A/B 对比观察（供 C 参考，非结论）

1. **B 条件更快**：A 组 `final_answer_after_turns_exhausted` 更多（13 vs 6），因为 A 在轮次用尽后还要补一次"请给出最终答案"的额外生成；B 中位耗时更低。
2. **B 触发 blocked 更少**（46 vs 102）：trace-first 反馈让模型更少撞调用上限——这是 A/B 差异的第一个信号，正确性层面待 C 的 scorer。
3. **同一任务跨条件同时耗尽预算**（`optimizing_bulk_purchase_discounts` 在 DEV 的 A/B 都撞 token 上限；`total_price_of_selected_items_1/_3` 在 EVAL 的 A/B 都撞轮次上限）：这些任务对"预算够不够"比"反馈怎么设计"更敏感，分析时应作为预算敏感组单独看待。

## 六、口径建议（留给 C 统一）

- `token_budget_exhausted` / `*_turns_exhausted` 建议单列为"预算受限"，不计入"错误率"；
- 工具 TypeError 是 episode 内事件，episode 最终可能仍给出正确答案，不应把"出过错"等同"失败"；
- 正确性一律以离线 scorer 对 `final_answer` 的判定为准。
