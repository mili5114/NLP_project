# C：代码贡献与讲解提纲

这份提纲用于交接和个人理解，不预设 code interview 的形式或评分标准。正式要求仍以 TA 回复为准。

## 讲解顺序与代码地图

| 问题 | 入口 | 应能解释 |
|---|---|---|
| 模型给出的 Answer 怎么判分？ | `src/evaluation/scoring.py`、`scripts/score.py` | numeric 的有限 Decimal 与 1e-6；string strip 后精确相等；无答案判失败；无答案也不能掩盖坏参考值 |
| 怎样知道 108 条数据真的完整？ | `audit.py`、`scripts/audit_results.py` | 官方任务清单 × condition；缺失/重复/异 split；版本与配置；逐轮 usage 与 episode 对账 |
| 为什么 blocked 多于上限不一定违规？ | `tool_audit.py` | 事件按真实调用次序；超限 blocked 不是执行，但仍消耗尝试；块内前序副作用保留；任务预算耗尽后不得再发交互轮 |
| Answer 与 final-only 有什么不同？ | `turns_reader.py`、`runtime_adapter.py` | 普通交互轮也可产出 Answer，384 上限；预算后的最终轮 128 上限且无工具；显式字段映射 |
| 怎么避免旧审计给新结果背书？ | `aggregation.py` 中 `validate_binding` | 指纹、唯一槽位、run/config 身份、布尔 success；不完整结果标 INCOMPLETE |
| 统计成本怎么做？ | `aggregation.py`、`plots.py` | 先逐任务加总所有调用再平均；失败进分母；缺 usage 不填 0；GPU-hours 不等于 episode wall time |

## 用真实缺陷讲清自己的贡献

DEV v4 的 `A / travel_itinerary_planning/multi_city_business_trip` 是现成案例：执行预算没有越界，但 32 次尝试后第 9–12 轮继续交互。C 补上状态转换审计和 6 项回归，使旧的有限 PASS 变成准确的 INCOMPLETE；额外输出 532 tokens 不能手工删除来“修好”结果。

展示证据：`docs/C_DEV_V4_REVIEW_20261125.md`、对应原始轨迹、新 `audit.json`、`tests/test_tool_audit.py` 和 `tests/test_audit.py`。这说明 C 不只是画图，也在实现可复现评分与协议验收。

## 自查练习

1. 用自己的话解释一次 score → audit → summarize → plot 的数据流，各步骤输入输出是什么。
2. 说明把 audit.complete 直接当真会出什么问题，找到一个 binding 回归测试。
3. 找到最终轮转换测试，解释合法同块 blocked 与非法下一交互轮的区别。
4. 说明为什么 v4 的 10/16 与 13/16 可以复算，却不能据此宣称最终效率结论。
5. 区分“已用 CPU 测试覆盖”“真实 GPU 路径触发”“尚未验证”，不扩大证明范围。

练习命令（CPU/离线，不加载模型）：

```powershell
python -m unittest discover -s tests -p test_scoring.py
python -m unittest discover -s tests -p test_tool_audit.py
python -m unittest discover -s tests -p test_aggregation.py
```

个人贡献的权威记录继续维护在 `docs/contributions/C.md`，与提交号、测试和实际交付物对应；不把他人 runtime/method 实现算作自己的工作。
