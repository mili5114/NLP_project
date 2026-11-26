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

| 报告位置 | 数字 | 来源 |
|---|---|---|
| 实验设置 §Throughput and deadline：DEV 有最终答案 | A 16/16、B 15/16 | `runs/dev_full_v5/stats.md` → `DEV/{A,B}/*/episode.json` 的 `final_answer` |
| 同上：离线正确率（DEV，仅本批） | A 10/16、B 13/16（总 23/32） | `runs/dev_full_v5/scored.jsonl`（`scripts/score.py` + `references/offline_reference_v1.json`） |
| 同上：中位耗时 / 最大耗时 | 30.0 s / 27.1 s、最大 122.2 s | `runs/dev_full_v5/stats.md`、各 `episode.json` 的 `wall_seconds` |
| 同上：截止时间证据 | `deadline_exceeded`=0，最大落盘延迟 0.016 s | 各 `episode.json` 的 `generation_stopped_at` / `episode_written_at` / `post_generation_seconds` |
| 同上：唯一无答案 | B `web_browsing/price_of_legendary_potion`，`no_answer_after_turns_exhausted` | `runs/dev_full_v5/DEV/B/.../episode.json` |
| 工具预算：执行/拦截 | 254 次执行、1 次拦截，每轮执行 ≤4、每任务 ≤32 | `scripts/check_budget_accounting.py --runs runs/dev_full_v5/DEV` |
| 解码速度 | 23.6–25.2 tok/s | 作业 14061564 的 `logs/run-14061564.out`（`scripts/env/bench_speed.py`） |
| 首轮 86 条（仅诊断） | DEV-A 15/16、DEV-B 14/16、EVAL-A 23/27、EVAL-B 25/27 | `runs/dev_baselines/`、`runs/eval_baselines/`、`docs/failure_taxonomy.md` |

## 3. 我实现的代码里最关键的三个决定

1. **答案隔离放在加载层，不放在 prompt 层**：上游 `Task.__init__` 会 `print_task()` 把标准答案打到 stdout。我在 `load_tasks()` 里整段重定向到内存缓冲并丢弃，而不是事后靠正则清洗日志——这样“答案是否进过进程”只有一个可检查的入口，配 `test_no_reference_leak` 与 `scripts/check_answer_isolation.py` 两层证据。
2. **180 秒用解码循环内的 `StoppingCriteria` 强制，并把“生成停止”与“落盘完成”记成两个时间戳**：只在轮与轮之间检查会让一次在途生成跨过截止点（v1 实测 236.5 s / 255.3 s）。分开两个时间戳是为了能证明 `wall_seconds` 里的差值不是停止/同步/序列化开销，而是真实生成时间。
3. **工具预算按“真实执行入口”计数，`blocked` 不执行但保留已执行效果**：用解释器内包函数来计数，而不是正则数文本（正则会把循环里的调用数错）。这带来一个可观测的副产品：`executed + blocked` 会超过上限，因为超限调用确实被模型发起了；这是合规形态，`scripts/check_budget_accounting.py` 按“只数执行”的口径复核。

## 4. 不属于我模块、但我能解释的失败案例

| task_id | 条件 | 现象 | 我的解释 |
|---|---|---|---|
| （不涉及具体任务） | — | C 的 `audit_results.py` 对合规数据报 `tool_attempts_per_action_exceeded`（某轮 5 个事件 > 4） | 审计按 `len(events)` 判上限，但第 5 个事件 `execution_status=blocked`、`result_repr=null`，即“发起但未执行”。课程要求正是“不执行超限调用”，所以应改为只统计非 blocked 事件；同一原因导致 `executed+blocked=48>32` 的第二个 error |
| （不涉及具体任务） | — | C 的 `score.py --episodes <目录>` 把 `manifest.json` 也当 episode，条数翻倍（64 vs 32） | `load_episodes()` 的目录模式用 `_looks_like_episode()` 判定，判据字段（`task_id`/`condition`）在 manifest 里也有；应改为要求 `final_answer` 或 `trajectory_path` 之类只属于 episode 的字段，或直接跳过名为 `manifest.json` 的文件。绕法：传 `index.jsonl` 显式索引 |

## 5. 工时与资源

| 项目 | 数值 |
|---|---|
| 人力工时 | 约 40 h（工程 30 / 文档 10） |
| GPU 作业数 / 卡时 | 实际启动 ≈ 20 个作业、≈ 2.3 GPU·h（含失败、预热与被撤销前已启动的作业） |
| 作业号区间 | 14051595 – 14100889（明细见 `docs/gpu_ledger.md`；课程上限 < 100 GPU·h，已用约 2%） |
