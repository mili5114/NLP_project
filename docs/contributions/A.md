# 个人贡献声明 — A（SibeiLYU）

> 只写自己这一份。定稿时间：D16 前。

## 1. 我负责的模块

| 模块 | 路径 | 我做了什么 |
|---|---|---|
| 模型后端 | `src/runtime/backend.py` | 本地 Transformers 推理封装，BF16 / greedy / non-thinking，真实 usage 统计 |
| Runner 与预算 | `src/runtime/runner.py`、`budget.py` | 12+1 轮、3072 tokens、16384 context、180s/15s、首个 Answer 即停、最终回答轮禁工具 |
| 执行器 | `src/runtime/executor.py` | 每任务新建解释器与 web tools，任务内变量保留，任务间重置 |
| 工具观察器 | `src/runtime/observer.py` | 7 字段事件、块内 4 次 / 任务 32 次真实入口计数、blocked 不执行但保留已执行效果 |
| 记录层 | `src/records/` | `manifest.json` / `turns.jsonl` / `episode.json` 与 token、hash、slug |
| A/B 基线反馈 | `src/feedback/baselines.py` | 条件 A 官方输出、条件 B Full Trace，共用 2000 字符上限 |
| 环境与版本 | `docs/setup.md`、`configs/versions.json`、`configs/locks/` | 集群环境、固定版本、依赖冻结、GPU 记录 |
| DEV 基线 | `runs/dev_baselines/sibei/` | 16 DEV × A/B = 32 次尝试，失败保留 |
| 报告章节 | `report/sections/background_setup.*` | 背景 / 系统 / 实验设置 |

## 2. 可追溯的报告数字

（填写格式：报告里的哪个单元格 → 结果表哪一行 → task/run → 配置 → 原始轨迹路径）

| 报告位置 | 数字 | 来源 |
|---|---|---|
|  |  |  |

## 3. 我实现的代码里最关键的三个决定

1. 
2. 
3. 

## 4. 不属于我模块、但我能解释的失败案例

（code interview 要求：至少一个别人的模块的失败案例）

| task_id | 条件 | 现象 | 我的解释 |
|---|---|---|---|
|  |  |  |  |

## 5. 工时与资源

| 项目 | 数值 |
|---|---|
| 人力工时 | 约 40 h（工程 30 / 文档 10） |
| GPU 作业数 / 卡时 |  |
| 作业号区间 |  |
