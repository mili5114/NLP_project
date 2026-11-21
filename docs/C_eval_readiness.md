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
| 四条件冻结包 | B | `configs/frozen/`、`configs/conditions/`、A/B/C/D 配置与 hash、课程附件 hash、模型/tokenizer revision、冻结时间与已知限制 |
| `frozen_run.md` | B | 四条件明确命令；C 不虚构 `run_eval.py` 之类命令 |
| DEV 候选与选择记录 | B | 最多三个候选的选择依据，确认 EVAL 不参与调参 |
| DEV 结果索引与资源账目 | A、B 各自 | C 只汇总，不清理或重跑他们的 DEV |
| GPU / 硬件与配额 | 团队 | 并发数、显存服务能力；不得用 180 秒上限推算整个项目用时 |

## 3. 正式执行顺序（到齐后）

1. 校验 freeze commit、配置 hash、环境与课程设置；建立 108 个唯一 task-condition 槽位的执行索引。
2. 用已有真实 DEV 日志做读取器健康检查。
3. 按 `frozen_run.md` 的命令运行 EVAL；原始日志先落盘，再离线评分与审计。答错、无答案、超时、预算耗尽都保留，不重跑到成功。
4. 基础设施故障导致有效尝试无法完成时，保留故障记录并按预先写明的恢复规则处理；方法/runner 修复需记录新 commit/config 与受影响范围。
5. 108 槽位完整、审计 PASS 后才生成正式主表、配对表与图；EVAL 不参与阈值选择或方法调参。
6. 结果分析、5–10 个配对案例、poster 与 demo 使用真实轨迹，相关章节交 B 合并进最终报告。

## 4. 合规提醒

- 「成员 C」是人员分工；「条件 C」是选择性反馈方法。两者不要混淆。
- 人员职责以 `TEAM_ASSIGNMENT.md` v2.0 为准，课程限制以 `configs/course/Assignment_Attachment.txt` 为准；旧方案如与新分工不同，采用新分工。
- 只展示可核验的数据。资源账目保留硬件、时间段、GPU 数、占用/计量方法，不把 `wall_seconds` 直接当 GPU hours，共享时间段避免重复计数。
