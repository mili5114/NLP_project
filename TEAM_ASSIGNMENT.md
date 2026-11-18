# Project 14 三人分工与交付清单

> v2.0，2026-11-18。本文件替代此前全部分工；研究技术协议仍见 PROJECT14_RESEARCH_PLAN.md。

> 开工准备已补齐：[接口约定](docs/interfaces.md)、[谁在什么时候交什么](docs/delivery_schedule.md)及 fixtures。时间表使用D0开工日到D21建议节点；A不再承担从零起草接口的前置工作，直接按既有约定适配真实运行。真实截止日期和GPU由团队在D0确认。

## 1. 最终分法：完整工作包，各有唯一负责人

| 成员 | 完整职责 | 主要交付物 | 不承担的其他工作 |
|---|---|---|---|
| A：基础平台与基线 | 本地模型环境、CodeAct runner、状态/预算、工具观察器、完整日志、官方 A/B；全部 DEV A/B 基线 | 可交接的运行平台、32 个 DEV 基线尝试及轨迹、环境文档、报告背景/设置章节 | 新方法设计、正式 EVAL、poster 排版 |
| B：改进方法与开发研究 | C/D 反馈插件、最多三个 DEV 候选比较、机制触发记录、方法选择、配置冻结 | C/D 插件、DEV 方法结果、冻结运行包、方法/消融章节、最终报告 PDF | 重建环境、重写观察器、正式 EVAL |
| C：正式评测与展示 | 离线评分、审计汇总、全量 EVAL、统计与错误分析、poster 和短演示 | 108 个 EVAL 任务条件结果、主表图、5–10 个配对案例、结果章节、成品海报与演示 | 平台开发、改进方法和 DEV 调参 |

每个任务只有一个 Owner。取消每人都跑九题、都分析一部分同类案例、都修改同一 poster 的安排。公平按完整模块的难度、人力投入及产物衡量，而非平均分题数。三人仍需各自准备个人代码面试。

## 2. A 的任务与交付

1. 固定课程规定的仓库 commit、模型/tokenizer revision、后端、BF16、greedy、non-thinking、seed 和 stop。
2. 实现 runner、解释器任务内状态与任务间重置、工具入口计数、时间/token/轮次预算、参考答案隔离、首个可解析 Answer 结束。
3. 实现工具事件观察器、JSONL 记录器、条件 A 官方输出和 B Full Trace。事件追踪只由 A 实现，B 消费事件，不再重复追踪。
4. 提供反馈插件入口，输入 Python 输出/事件/配置，输出可见反馈和选择元数据。
5. 跑全部 16 DEV 的 A/B，共 32 个任务尝试。保留失败，记录变量与反馈关系的注释案例。
6. 交运行说明和背景/系统/实验设置章节。

交付路径：`src/runtime/`、`src/records/`、`src/feedback/baselines.py`、依赖锁文件、`configs/versions.json`、`docs/setup.md`、`docs/interfaces.md`、`runs/dev_baselines/`、`report/sections/background_setup.*`。

交付标准：B 按文档能运行一个 DEV 并接入插件，C 能从 JSONL 读到真实模型/工具调用、代码、返回、反馈、预测和 tokens；所有 DEV A/B 任务都有记录。平台缺陷仍由 A 修复，B/C 不各自另建平台。

## 3. B 的任务与交付

1. 使用固定事件 fixture，独立实现研究方案的 C 选择规则和 D 消融。两者同格式/预算，只改变筛选规则。
2. 收到 A 的 DEV 基线后检查完整失败与反馈现象，形成真实证据支持的方法动机。实现可以提前写，实证解释必须基于真实数据。
3. 使用 C 的离线评分 CLI，在全部 16 DEV 上比较最多三个候选，按预先确定的成功数、input tokens、候选编号规则选择；保存所有尝试。
4. 完成最终 D 的 DEV 检查，记录筛选触发、实际反馈改变及后续行为证据。
5. 在已交付平台上接入插件，写出固定版本/hash、条件配置、freeze manifest 和运行说明，交给 C。
6. 写方法/消融章节；收到 A/C 的章节成稿后，负责统一报告模板与排版，输出最终报告 PDF。

交付路径：`src/feedback/selective.py`、C/D renderer、`configs/conditions/`、`docs/method.md`、候选登记表、`runs/dev_methods/`、`configs/frozen/`、`docs/frozen_run.md`、`report/sections/method.*`、`report/final_report.pdf`及源文件。

交付标准：C 能按 frozen_run 文档运行四条件；候选不超过三个，选择只依赖 DEV；C/D 区别可追溯。方法没有提升也可以完成研究交付，不用 EVAL 反调参数。

## 4. C 的任务与交付

1. 按官方 JSON 实现 split 校验、离线 scorer、完整性审计、tokens/成本汇总和图表入口。先用 synthetic JSONL 开发，之后读取真实格式。
2. 在 A/B 正式 DEV 比较前交付 scorer CLI，供他们自己评分。C 不替 A/B 整理或补跑 DEV。
3. 收到 B 的冻结包后运行全部 27 EVAL 的 A/B/C/D，共 108 个 task-condition 结果槽位。普通失败、无答案、超时和预算耗尽都保留，不重跑到成功。
4. 生成逐任务表、主表、配对结果、成本图和完整性审计；汇总 A/B 交来的 DEV 资源记录与自己的 EVAL 记录。
5. 完成 5–10 个有证据的配对案例。按预先方法选例，区分信息不足、误用、新问题和其他执行失败；证据不足写不确定，不要求三人重复标注。
6. 写结果/错误分析/局限章节；制作整张 poster、短演示素材及离线回放脚本，使用已有轨迹，不开发第二套运行器。

交付路径：`src/evaluation/`、`scripts/score.py`、`audit_results.py`、`summarize.py`、绘图入口、`runs/eval/`、`results/per_task.csv`、主表/配对表/成本图、`docs/cases.md`、`report/sections/results_analysis.*`、`report/poster.*`、`report/demo/`。

交付标准：失败全部计入 27 个任务分母；数值 Decimal、有限值且误差不超过 1e-6；字符串 strip 后 exact match；tokens 覆盖每题全部调用和失败；表图可从原始结果再生成。

## 5. 并行开始，按成品接力

第一天 A 提供最小接口和 JSONL 示例，确认后内部实现各自决定。A 是在线日志格式 Owner，B 是方法配置 Owner，C 是离线评分结果格式 Owner。

```text
A：平台/观察器/记录器/A-B ──交平台和全DEV基线──┐
B：fixture上开发C-D/方法文稿 ─接入、DEV候选──冻结包──┐
C：synthetic日志上开发评分/审计/绘图 ─交评分CLI────全EVAL→统计/海报
```

A 可先用 stub feedback。B 不等 GPU，先写插件和方法说明。C 不等真实结果，先写评分工具和 poster 模板。真实候选选择依赖 DEV，正式 EVAL 依赖冻结包，最终结果依赖真实日志；这是必要顺序。

| 交接 | 前一位完成后交什么 | 接手者做什么 |
|---|---|---|
| A → B | 固定 commit、平台、插件接口、DEV A/B 日志 | B 接入方法并比较候选 |
| C → A/B | scorer/auditor CLI、使用说明 | A/B 各自评分自己的 DEV runs |
| B → C | 冻结代码/配置/hash、四条件运行命令、已知限制 | C 运行全 EVAL |
| A/B → C | 自己的 DEV run 索引和 GPU ledger | C 汇总全项目成本 |
| A/C → B | 报告章节成稿、引用、图表路径 | B 合并排版报告 |

每次交接仅需 commit、文件路径、命令和已知限制。缺陷发回原 Owner，不由接手者同时改同一模块。不安排每日会议；平时自己的 Issue 留进度和具体阻塞即可。

## 6. 公平与工作量

每人内部可先按约 40 小时规划（可同比缩放，不是课程要求或实测预测）：

- A：工程/基线约 30h，文档/章节约 10h。
- B：方法/DEV约 30h，方法章节/报告排版约 10h。
- C：评测工具/正式运行管理约 18h，统计案例约 14h，poster/演示约 8h。

GPU 等待和无人值守运行不等于人力投入。上述只是初始估计，不能保证天然精确相等。仅在交接节点看实际负担；一人明显超负荷时，把一个未开工的完整产物整体移交并换 Owner，例如 poster 成品整体由 C 转给 A，或报告排版整体由 B 转给 A。避免分摊细碎步骤导致沟通增加。

每人独立阅读其他模块说明，准备个人代码面试，不重复实现他人模块。

## 7. 课程必交材料与负责人

依据本地 Project 14 说明（PDF 第54–55页）和 Assignment_Attachment.txt。路径为团队约定，最终上传格式按教师通知。

| 必交内容 | 建议文件 | 最终负责人 |
|---|---|---|
| 最多六页正文报告，参考文献/附录除外 | `report/final_report.pdf`及源文件 | B；A/C 交各自章节成稿 |
| 可运行代码和使用说明 | runtime/records/baselines、feedback、evaluation | A/B/C 各负责互斥目录；README 归 A |
| 依赖、代码/模型/后端版本记录 | lock 文件、`configs/versions.json` | A，B/C 提交依赖信息给 A |
| 实验配置、冻结记录 | `configs/conditions/`、`configs/frozen/` | B |
| 原始 task IDs、split | 原样保存官方 `split_manifest.json` | A 归档，C 校验和使用 |
| 原始预测、逐任务评测结果 | `runs/eval/`、`results/per_task.csv` | C；DEV 结果分别归 A/B |
| 完整交互日志 | `runs/dev_baselines/`、`dev_methods/`、`eval/` | A/B/C 各一个目录 |
| GPU 使用记录 | 各 run ledger + 总成本表 | A/B 各交自己的，C 汇总 |
| Poster | `report/poster.pdf`及源文件 | C |
| 短演示、同任务反馈对照 | `report/demo/` | C，使用真实轨迹和现成平台 |
| 个体贡献声明 | `docs/contributions/A.md`、`B.md`、`C.md` | 每人只写自己的文件 |

完整轨迹包含模型与工具调用、生成代码、工具返回、可见反馈和最终答案；所有失败保留。实验程序直接读取两份课程 JSON，遵守模型/预算/答案隔离/首个 Answer 结束等要求。

## 8. 进度与 GitHub Issues

| 阶段 | A | B | C |
|---|---|---|---|
| 前期 | 给接口/fixture，搭平台 | fixture上写C/D和配置 | synthetic上写评分与图表工具 |
| 中期 | 完成全DEV A/B并交接 | 接收平台后做候选、冻结 | 交评分入口，适配真实日志 |
| 正式实验期 | 写设置章节/README | 写方法章节/冻结文档 | 全EVAL、统计、案例 |
| 交付期 | 完成个人贡献和面试准备 | 合并报告输出成品 | 输出结果包、poster、演示 |

建立 A-platform、A-dev-baselines、B-feedback、B-dev-freeze、C-evaluator、C-eval-analysis、B-final-report、C-poster-demo 八类 Issue，每项一个 Owner。日期按实际截止日填，不预设四周一定可用。
