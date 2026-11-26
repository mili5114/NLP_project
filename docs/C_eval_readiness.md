# 正式 EVAL 就绪度清单

本轮只完成离线工具与合成端到端验证。**没有下载模型、没有运行正式 EVAL、没有产生任何实验数字。** 正式 EVAL 必须等 A 的平台和 B 的冻结包到位。

## 1. 已就绪（C 侧）

- [x] 离线评分器、输入读取、CLI 与 35 个单元测试通过。
- [x] 完整性审计：108 槽位校验、缺失/重复/未知/错误 split、token 一致性、synthetic 门控、预算核验。
- [x] 汇总与配对：成功率、tokens、调用数、耗时、C vs B / C vs D；不完整数据标 INCOMPLETE。
- [x] 图表入口：成功率、token 成本、配对结果；合成图带 `SYNTHETIC — NOT EXPERIMENTAL RESULTS`。
- [x] 合成端到端：评分 → 审计 → 汇总 → 图表全部跑通（12 槽位，2 个有记录的失败）。

## 2. 仍缺的内容与 Owner

| 缺口 | 需要谁提供 | 具体物 |
|---|---|---|
| 可用运行平台与真实 runner 命令 | A | 固定 commit、`configs/versions.json`、依赖锁文件、运行命令、环境变量、`initial_contract` 注入证据 |
| 真实 episode / turns / manifest 样例 | A | 字段说明与一份可解析样本；C 用它做 turns 适配层的一次映射 |
| 在线答案隔离证据 | A | 参考答案与任务定义未进入模型输入/代码环境的证据 |
| 固定版本离线参考答案导出 | A（源数据）+ C（校验） | 27 个 EVAL 任务的 `task_id` / `answer_type` / `reference`，只进离线文件 |
| 四条件冻结包 | B | `configs/frozen/`、`configs/conditions/`、**每个条件各自的 config hash**（A/B/C/D 允许不同，审计按条件核对）、课程附件 hash、模型/tokenizer revision、冻结时间与已知限制 |
| 正式版本三元组 | A + B | code commit、model revision、每条件 config hash；正式审计缺任一项即 FAIL，不能跳过仍宣称通过 |
| turns 字段语义确认 | A | 确认 `produced_final_answer`（交互轮可产出 Answer）与 `is_final_answer_turn`（128 上限的 final-only 轮）对应 A 的实际字段名 |
| `frozen_run.md` | B | 四条件明确命令；C 不虚构 `run_eval.py` 之类命令 |
| DEV 候选与选择记录 | B | 最多三个候选的选择依据，确认 EVAL 不参与调参 |
| DEV 结果索引与资源账目 | A、B 各自 | C 只汇总，不清理或重跑他们的 DEV |
| GPU / 硬件与配额 | 团队 | 并发数、显存服务能力；不得用 180 秒上限推算整个项目用时 |

## 3. 正式执行顺序（到齐后）

1. 校验 freeze commit、每条件 config hash、code commit、model revision、环境与课程设置；建立 108 个唯一 task-condition 槽位的执行索引。
2. 用已有真实 DEV 日志做读取器健康检查。
3. 按 `frozen_run.md` 的命令运行 EVAL；原始日志先落盘，再离线评分与审计。答错、无答案、超时、预算耗尽都保留，不重跑到成功。
4. 基础设施故障导致有效尝试无法完成时，保留故障记录并按预先写明的恢复规则处理；方法/runner 修复需记录新 commit/config 与受影响范围。
5. 108 槽位完整、审计 PASS 后才生成正式主表、配对表与图；EVAL 不参与阈值选择或方法调参。
6. 结果分析、5–10 个配对案例、poster 与 demo 使用真实轨迹，相关章节交 B 合并进最终报告。

## 4. 合规提醒

- 「成员 C」是人员分工；「条件 C」是选择性反馈方法。两者不要混淆。
- 人员职责以 `TEAM_ASSIGNMENT.md` v2.0 为准，课程限制以 `configs/course/Assignment_Attachment.txt` 为准；旧方案如与新分工不同，采用新分工。
- 只展示可核验的数据。资源账目保留硬件、时间段、GPU 数、占用/计量方法，不把 `wall_seconds` 直接当 GPU hours，共享时间段避免重复计数。

## 2026-11-23 状态更新

A 已上传首轮真实 DEV/EVAL A/B 日志。C 已完成32条 DEV 的字段适配与有限结构核验，但发现提示签名与预留最终轮问题；尚未正式认证或评分。最新交接和阻碍以 docs/C_REAL_LOG_REVIEW_20261123.md 为准；旧清单中的“缺真实日志”已由该更新替代。

## 2026-11-24 更新

A 已在 beacbfc 修复签名与预留最终轮代码，修复版真实日志仍待交付；C 已修正 blocked 审计误报。最新状态见 docs/C_FOLLOWUP_20261124.md。旧日志不因代码更新自动成为合规数据，不应覆盖旧记录。

## 4条修复样例已到（同日后续）

新样例已完成部分验收，完整32条基线仍未到。时间边界、版本可追溯性与验证范围见 docs/C_FIX_SAMPLE_REVIEW_20261124.md。此前“没有修复后日志”的描述仅是历史状态。


## 2026-11-25：DEV v4 独立验收

详见 [C DEV v4 验收](C_DEV_V4_REVIEW_20261125.md)。32/32 结构及评分复现通过，但 1 槽位工具预算耗尽后继续交互；新增转换审计与 6 项回归，当前 132 tests 通过。v4 结论为 INCOMPLETE，仅作诊断，等待 A 修复运行时、B 对齐协议后冻结。参考原文留本机，未跑新 GPU/EVAL。


## 2026-11-25：冻结前可并行推进的 C 材料

- [正式 EVAL 执行与验收手册](C_EVAL_EXECUTION.md)：关口、交接字段、故障恢复和带退出码检查的离线命令。
- [结果章节骨架](../report/sections/03_results.md)：主表、配对方向、案例选择和局限；无正式数值。
- [Poster/demo 底稿](C_POSTER_DEMO_PLAN.md)：内容、演示步骤和成品清单，形式/时长待课程确认。
- [C 代码讲解提纲](C_CODE_WALKTHROUGH.md)：代码地图、真实缺陷和自查练习。

这些是可用准备稿，不是已完成的正式 EVAL、poster PDF 或视频。C/D 接入及统一协议冻结仍是正式运行前置条件。

## 2026-11-25：工具预算修复通过代码 / CPU 复核

已合入并复核 main 的 de5b037。C 新增两项独立集成回归，证明 32 次累计尝试即使仅 4 次执行、28 次 blocked，也直接进入禁工具的最终轮；合并后全套 138 项测试通过。详见 C_TOOL_BUDGET_FIX_REVIEW_20261125.md。可以开始新版 32 条 DEV A/B，数据仍待实际推送后验收；v4 的 INCOMPLETE 不变，尚未开始正式 EVAL。

## 2026-11-26：DEV v5 独立验收通过

数据提交 0f14010，运行代码 de5b037。C 审计 32/32、0 error / 0 warning，独立评分逐条一致（A 10/16，B 13/16），汇总 COMPLETE，138 项 CPU 测试通过。真实工具预算转换已覆盖；真实 deadline 截断和 string_length 仍未覆盖。作业原始日志已交付。详见 C_DEV_V5_REVIEW_20261126.md；下一阶段等待 B 方法/冻结包，不启动正式 EVAL。
