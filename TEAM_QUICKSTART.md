# Project 14 三人认领页

> 项目：Execution Feedback and Interaction Efficiency in CodeAct Agents  
> 课程：AIAA 4051，2026 Fall  
> 状态：A 已认领（[#1](https://github.com/mili5114/NLP_project/issues/1)，SibeiLYU）；C 已认领（郑启丹/mili5114，工作痕迹见 [PR #3](https://github.com/mili5114/NLP_project/pull/3)）；**B 待认领（关键路径：方法冻结 + 配置，阻塞 EVAL 与报告合并）**。下面是三个完整工作包，一人认领一个，不按题目拆人。

## 一眼看懂谁干什么

| 角色 | 一句话 | 你交什么 | 你不做什么 | 认领人 |
|---|---|---|---|---|
| **A 平台与基线** | 把官方 CodeAct 在本地跑起来，产出 A/B 两个基线的 DEV 结果 | 可运行 runner、工具观察器、完整日志、16 DEV × A/B = 32 次轨迹、实验设置章节、README | 新方法设计、正式 EVAL、poster | **SibeiLYU**（[#1](https://github.com/mili5114/NLP_project/issues/1)） |
| **B 方法与冻结** | 设计 C/D 反馈策略，在 DEV 上选一个配置并冻结 | C/D 插件、最多 3 个候选的比较记录、freeze manifest、方法章、最终报告 PDF | 搭环境、重写观察器、跑 EVAL | 待填 |
| **C 评测与展示** | 离线评分、跑全部 EVAL、做统计案例和展示材料 | scorer / 审计 / 汇总脚本、27 × 4 = 108 个结果槽位、主表图、5–10 个配对案例、poster、demo | 平台开发、方法调参 | 待填 |

工作量按约 40 小时/人规划，公平按完整模块衡量，不按题数平均。GPU 等待不算人力投入。

## 四条硬规矩

1. 每个文件 / 目录只有一个 Owner，别人不改，缺陷发回原 Owner。
2. EVAL 只能在冻结后跑；参考答案只进离线评分，不进 agent 上下文。
3. 失败任务全部保留，27 个任务全部进分母，不许重跑到成功。
4. 每次交接附**一页代码地图 + 15 分钟讲解**。个人 code interview 占 12%，每人都要能追溯至少一个报告数字、解释一个不属于自己模块的失败案例。

## 节奏（D0 = 认领完成日）

- **D0–D5：三人零依赖并行。** A 搭平台；B 在 fixture 上写 C/D；C 在 synthetic 日志上写评分器。
- **D5–D7：** A 交 DEV A/B 基线 → B。
- **D7–D10：** B 交冻结包 → C。
- **D10–D14：** C 跑全量 EVAL；A/B 写各自章节。
- **D14–D21：** C 出统计 / 案例 / poster / demo；B 合并报告 PDF；三人准备面试。

## 怎么认领

1. 在本仓库建一个 issue，标题写「认领 A + 你的名字」（或 B / C）。
2. issue 里写清楚：选的角色、GitHub ID、GPU 来源和大概配额、课程实际截止日（如果知道）。
3. 三个角色都有人认领后，把上面表格的「认领人」填上名字，**当天算 D0**。

## 详细文档

- 分工与交付验收：[TEAM_ASSIGNMENT.md](TEAM_ASSIGNMENT.md)
- 研究方案（方法 / 预算 / 评测协议）：[PROJECT14_RESEARCH_PLAN.md](PROJECT14_RESEARCH_PLAN.md)
- 接口约定：[docs/interfaces.md](docs/interfaces.md)
- 交付时间表：[docs/delivery_schedule.md](docs/delivery_schedule.md)
- 课程原始附件（原样保存）：`configs/course/`
