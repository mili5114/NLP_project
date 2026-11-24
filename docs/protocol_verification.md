# 协议验证表（A 维护）

> 口径：**已验证** = 有真实运行记录或可复跑的测试为证；**待验证** = 只有代码路径、没有证据；
> **未覆盖** = 有测试但真实样例从未走到该分支（如实标注，不算通过）。
> 一键复跑：`python -m unittest discover -s tests`（101 条）、`python scripts/check_answer_isolation.py --runs runs`。

| # | 附件要求 | 证据 | 状态 |
|---|---|---|---|
| 1 | 原始 contract、最终回答请求、固定生成设置原样生效 | ① `configs/course/runtime_settings.json`（sha256 `faa79929…dfdd1`）里的 `initial_contract` / `final_answer_request` 原文；② 真实记录核对：`runs/dev_fix_check_v2/DEV/{A,B}/*/turns.jsonl` 第 0 行 `messages[0]` 含 contract 全文，最终轮 `messages[-1]` 恰为最终回答请求；③ 生成设置：`backend.py` 固定 `do_sample=False`、`enable_thinking=False`、EOS 248044/248046、stop `End Action`，逐轮写在 `generation_settings` | 已验证（真实样例） |
| 2a | token 上限：每轮 384、总量 3072、预留最终轮 128 | `tests/test_runtime_cpu.py::BudgetLimitTest::test_turn_cap_is_384_and_reserve_is_128`；真实：v2 A/B 生成 2954/3072，最终轮 128 | 已验证 |
| 2b | 轮次上限 12 | `::test_turn_budget_exhausted_then_final_answer`（12 交互轮 + 1 最终轮）；真实：v2 A/B `turns_used=8` 后因 token 进最终轮 | 已验证 |
| 2c | 上下文 16384 | `::BudgetLimitTest::test_context_cap_zeroes_generation`（超限则该轮分配 0）；真实：单次调用最大 `input_tokens=4403` | 单测已验证；真实样例**未覆盖**（从未接近上限） |
| 2d | 工具次数：块内 4 / 任务 32 | `::test_fifth_call_in_block_is_blocked`、`::test_task_level_limit_32`；真实：DEV-A `multi_city_business_trip` 32 executed + 4 blocked，DEV-B `adventure_trip` 14 + 2 | 已验证 |
| 2e | 时间：任务 180s、代码块 15s | `::test_generate_receives_task_deadline`、`::test_deadline_cut_records_generation_stop_and_persist_separately`（把 `task_seconds` 缩到 0.2s 复现到点截断）；代码块超时用剩余任务时间钳制（`runner.py` 的 `min(action_seconds, seconds_remaining)`） | 单测已验证；**真实样例未覆盖**（v2 两集 124s/140s，未触及 180s） |
| 3 | 首个可解析 Answer 结束，不按正确性重试 | `::test_first_answer_stops_immediately`；`Task.parse_generation` 只解析、不比较参考（`check_answer` 在 runner 中从不调用）；真实：v1 `travel` A 第 4 次调用即 `Answer: 615` 结束；首轮基线 `message_decoder/multi_step_decoding_challenge` A 给出与参考不同的 `MySantwor` 也照样结束、未重跑 | 已验证 |
| 4 | 任务间重置、任务内变量保留 | 每个 episode 重新 import 任务模块 + 新建 IPython shell，命名空间只含工具函数（`tasks.py::load_tasks`、`repl.py::BlockExecutor`）；`::test_variables_reset_between_tasks`；任务内保留见 `docs/task1_annotated_sample.md` §4 的真实轨迹（DEV-A `interstellar_trade_transaction`） | 已验证 |
| 5 | blocked 不执行，之前的效果保留 | `::test_blocked_call_keeps_earlier_effects`、`::test_task_level_limit_32`；真实：DEV-A `multi_city_business_trip` 被拦截的调用"未执行"但块内其余语句照常跑、既有变量不丢（该 episode 32 executed / 4 blocked 后仍进入最终轮） | 已验证 |
| 6a | 参考答案不进在线记录 | `scripts/check_answer_isolation.py --runs runs` → `PASS: no reference-answer trace`（279 文件 / 93 episode 目录）；`::test_no_reference_leak` | 已验证 |
| 6b | 参考答案不进模型输入与可见反馈 | runner 只把 `python_output` 与工具事件交给反馈层，`expected_output` 从不进 `messages`；上游 `Task.print_task()` 的打印被 `contextlib.redirect_stdout` 丢弃（`tasks.py::load_tasks`） | 已验证 |
| 6c | 含答案的任务定义与**代码执行环境**隔离 | 执行命名空间 `task._ns` 只放工具函数；但同进程内工具函数的 `__globals__` 仍能回到任务模块，理论上可读到 `TASKS[*].expected_output`。当前靠 contract（"Do not inspect tool internals"）+ 轨迹扫描把关，**没有硬沙箱** | 部分验证（需写进 Limitations） |
| 6d | 离线参考答案不进公开仓库、不进执行环境 | `references/offline_reference_v1.json` 被 `.gitignore` 挡住，只提交 `*.manifest.json`（`answers_in_git: false` + 逐条 `reference_sha256`）；`scripts/export_references.py` 拒绝写入 `runs/`、`src/`、`configs/course/`、`third_party/` | 已验证 |
| 7 | A/B 反馈格式与可见长度符合附件 | A=Python 输出原文（`::test_condition_a_returns_python_output_verbatim`）；B=trace 前缀 + 每事件一行 + `Python output:`（`::test_condition_b_puts_trace_first`）；上限 2000（`::test_condition_b_respects_2000_limit`）；真实样例见 `runs/dev_baselines/DEV/B/*`：`[1] convert_hex_to_ascii args=313233 kwargs= [ok] -> 123` … | 已验证 |

## 需要写进报告 Limitations 的两条

1. **执行环境没有硬隔离**（6c）：同进程 Python，工具函数可回溯到模块全局。协议要求的是行为约束（contract 明令禁止检查工具内部），我们靠 contract + 全量轨迹扫描证明"没有发生"，而不是靠沙箱"不可能发生"。
2. **180s 到点截断、上下文 16384 上限没有真实样例**：前者只有 CPU 回归（真实两集都是 124s/140s 正常结束），后者真实单次调用最大 4403 token。写报告时不能说"已在真实运行中验证"，只能说"由回归测试覆盖"。
