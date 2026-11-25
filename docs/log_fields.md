# 日志字段说明（A 维护）

> 适用版本：`fc67310` 及以后写入的记录。更早的数据（`7af057d` 及以前）没有显式时间戳字段，
> 只能用第 3 节的派生口径复算，见 §7。
> 字段名适用版本：`8be4109` 起对齐 C 的 reader（§4.3）；`7af057d` 及以前的批次用旧字段名，读法见 §4.3 的换算表。

## 1. 目录与三件套

```text
runs/<batch>/<SPLIT>/<COND>/<task_id>__<run_id>/
    manifest.json   这次运行固定了什么（可独立复现）
    turns.jsonl     每次模型调用一行（含最终回答调用）
    episode.json    这次运行的结论性字段
```

- 一个 episode = 一个 task × 一个 condition。`<batch>` 是批次目录（`dev_baselines` / `dev_fix_check` / `dev_fix_check_v2` / `dev_full_v3` …），批次含义见 `runs/index.md`。
- 目录名是安全 slug（非字母数字压成 `_`），原始 `task_id` 保留在文件字段里。
- 在线记录里**没有** `reference_answer` / `success`：标准答案只存在于离线参考文件，评分由 C 的 `scripts/score.py` 离线做。

## 2. 时间口径：180 秒是任务截止，185 秒只是工程检查线

| 量 | 含义 | 字段 |
|---|---|---|
| 任务开始 | 该 episode 的预算起点 | `task_started_at`（本地时区 ISO） |
| 任务截止 | 开始 + `limits.task_seconds`（=180s） | `task_deadline_at` |
| 生成停止 | **最后一次**模型生成返回的时刻（被 180s 截断时就是截断时刻） | `generation_stopped_at` / `generation_stopped_task_seconds` |
| 最终落盘 | `episode.json` 真正写出的时刻 | `episode_written_at` / `episode_written_task_seconds` |
| 落盘开销 | 落盘 − 生成停止 | `post_generation_seconds` |
| 超截止 | 落盘时刻 − 180s（不足 180 记 0） | `deadline_overrun_seconds` / `deadline_exceeded` |

判读规则：

- **协议合规**看 `generation_stopped_task_seconds ≤ 180`（模型在截止前/到点停止）。
- **工程检查**看 `episode_written_task_seconds ≤ 185`（含停止、同步、落盘的额外 ≤5s 开销）。
- 两者不能混成一句"跑了 182 秒所以超时"：182s 的落盘时刻对应的是 180s 内的生成，超出部分只是写文件。
- 被截止截断的那一轮仍然落盘，`finish_reason = deadline`、`cut_by_deadline = true`、`action = null`（不执行代码、不进最终轮）。

## 3. `episode.json`

| 字段 | 说明 |
|---|---|
| `schema_version` | 记录格式版本（当前 `"1"`） |
| `synthetic` | 真实运行恒为 `false`；fixture 数据为 `true`，不得混入结果 |
| `run_id` | `<SPLIT>-<COND>-<slug>-s<seed>` |
| `task_id` / `split` / `condition` | 原始 task_id；`DEV`/`EVAL`；`A`/`B`/`C`/`D` |
| `status` | `completed` / `timeout` / `no_answer` / `error` |
| `termination_reason` | 见 §6 词表 |
| `final_answer` | 首个可解析 `Answer:` 的内容；无答案为 `null`（不是空串） |
| `input_tokens` / `output_tokens` | 本题全部调用的真实 tokenizer 计数之和 |
| `model_calls` | 模型调用次数（最终轮也算一次） |
| `tool_attempts_executed` / `tool_attempts_blocked` | 实际执行 / 被限额拦截（blocked 计入尝试、不计入执行） |
| `wall_seconds` | writer 生命周期墙钟（≈ 任务总时长，含落盘） |
| `trajectory_path` | 对应 `turns.jsonl` 路径 |
| `config_sha256` | 课程 `runtime_settings.json` 的 sha256（见 `docs/env_and_config.md` §3，注意这不是完整配置 hash） |
| `code_commit` / `model_revision` | 该记录实际使用的团队 commit 与模型 revision（`8be4109` 起；旧批次从 `manifest.json` 读） |
| 时间字段 | 见 §2 |
| `error` | 仅 `status=error` 时出现：`<ExcType>: <message>` |

## 4. `turns.jsonl`

每行一次模型调用。字段名与 C 的 `turns_reader.REQUIRED_TURN_FIELDS` 对齐（`8be4109` 起）。`turn_index` 从 1 递增；更早批次从 0 起，差异见 §4.4。

| 字段 | 说明 |
|---|---|
| `turn_index` | 1 起的调用序号 |
| `is_final_answer_turn` | 本行是预算耗尽后追加的**纯回答轮**（受 128 token 限制、不执行工具） |
| `produced_final_answer` | 本行的解析结果就是最终 Answer（可能是普通交互轮，仍受 384 限制） |
| `messages` | 本次调用**实际送入**的完整 messages（system + 历史 assistant/user） |
| `generation_settings` | `max_new_tokens`、`do_sample=false`、`enable_thinking=false`、`stop_text`、`is_final_turn` |
| `raw_model_text` / `parsed` | 模型原始文本 / 解析结果（`answer` / `action` / `invalid`）；`parsed_action` 与 `parsed` 同值 |
| `action` | 被执行的代码块；`null` 表示本行没有执行代码（Answer、最终轮、被截止截断、无效输出） |
| `events` | 工具事件列表，字段见 §4.1；无调用为 `[]` |
| `python_output` | 解释器 stdout（未截断原文；模型看到的可能已被反馈层截断） |
| `feedback` | **实际送回模型**的反馈（A：Python 输出原文；B：trace 优先 + Python 输出） |
| `feedback_metadata` | `selected_event_indices` / `omitted_event_indices` / `truncated` / `feedback_chars` / `rule_trigger_count`；特殊轮次另有 `note` |
| `input_tokens` / `output_tokens` | 本次调用的真实计数 |
| `elapsed_seconds` | 生成 + 代码块执行（`wall_seconds` 同值，供 C 的 reader 取用） |
| `generation_seconds` | **只有**模型生成耗时 |
| `finish_reason` | `stop`（遇到停止串/EOS）/ `length`（达到本次 token 上限）/ `deadline`（被 180s 截断） |
| `cut_by_deadline` | `finish_reason == "deadline"` |
| `generation_stopped_at` / `generation_stopped_task_seconds` | 本次生成结束时刻（ISO / 相对任务起点秒数） |
| `budget` | 本行结束后的预算快照：`turns_used`、`turns_left`、`generated_tokens`、`remaining_generated`、`final_turn_used`、`elapsed_seconds` |

### 4.1 工具事件（7 字段）

`index`（块内从 1 开始）、`tool`、`args_repr`、`kwargs_repr`、`execution_status`（`ok`/`error`/`blocked`）、`result_repr`、`error_repr`、`elapsed_seconds`。不适用项写 `null`。`blocked` 表示**没有执行**，不是正常返回。

### 4.2 最终回答轮的识别

| 问题 | 判据 |
|---|---|
| 这次调用是不是"预算耗尽后追加的纯回答轮"？ | `is_final_answer_turn == true`（冗余判据：`generation_settings.is_final_turn`、`max_new_tokens=128`、不执行工具） |
| 这次调用是不是"普通交互轮里直接给出 Answer"？ | `produced_final_answer == true` 且 `is_final_answer_turn == false`（上限仍是 384） |
| 这一轮为什么没有执行代码？ | `feedback_metadata.note`：`final_answer_only_turn` / `generation_cut_by_task_timeout` / `invalid_generation` |

两个标志必须分开记、分开验：交互轮直接答对时只有 `produced_final_answer`，不能据此套 128 的限制；最终轮只用于"预算已耗尽仍要一句话"的场景。注意 `final_turn_used` 只在 `budget` 快照里出现，且表示"最终轮已被用过"，与 `is_final_answer_turn`（本行就是最终轮）不要混用。

### 4.3 与 C 的 schema 的对应关系

`8be4109` 起运行时直接写 C 的字段名（`turns_reader.REQUIRED_TURN_FIELDS` 全覆盖），`episode.json` 自带 `code_commit` 与 `model_revision`，C 侧不需要任何映射。

`8be4109` 之前的批次（`runs/dev_fix_check*`、`runs/dev_full_v3` 等）仍用旧字段名，读老批次时按下表换算：

| C 期望的字段 | 旧批次实际字段 | 换算规则 |
|---|---|---|
| `is_final_answer_turn` | `generation_settings.is_final_turn` | 直接取 |
| `produced_final_answer` | `parsed.type == "answer"` | 布尔化 |
| `raw_model_text` | `raw_text` | 直接取 |
| `events` | `tool_events` | 直接取 |
| `feedback` | `feedback_text` | 直接取 |
| `turn_index` | `turn_index` | **加 1**（旧批次 0 起） |
| episode 的 `code_commit` | `manifest.team_commit` | 直接取 |
| episode 的 `model_revision` | `manifest.model.revision` | 直接取 |

正式基线用 `runs/dev_full_v4`（`8be4109`，原生字段名），旧批次只作诊断材料，不必为读它们改代码。



## 5. `manifest.json`

| 字段 | 说明 |
|---|---|
| `schema_version` / `started_at` | 格式版本 / 开始时间（本地时区 ISO） |
| `run_id` / `split` / `condition` / `seed` / `task_id` / `tasks` | 运行标识 |
| `model` | `repository`、`revision`、`dtype`、`enable_thinking`、`seed`、`eos_token_ids` |
| `backend` | `transformers`（本地 HF 推理） |
| `upstream_commit` | 课程指定上游 commit |
| `team_commit` | 本仓库运行时代码 commit（**不是**数据提交） |
| `course_hashes` | 三个课程文件的实测 sha256；`_declared` 是教师给的；`_mismatched` 为空表示一致 |
| `limits` | 本次生效的全部上限（轮次/token/上下文/工具次数/时间/反馈长度） |
| `stop_text` | 停止串 |

GPU 型号不进 manifest（它不改变协议），记录在 `docs/gpu_ledger.md` 与作业脚本里。

## 6. `termination_reason` 词表

| 值 | 含义 |
|---|---|
| `answer` | 交互轮里出现首个可解析 Answer，立即结束 |
| `final_answer_after_turns_exhausted` | 12 轮用尽 → 追加最终轮 → 拿到 Answer |
| `final_answer_after_tokens_exhausted` | 生成预算只剩预留 128 → 最终轮 → 拿到 Answer |
| `no_answer_after_turns_exhausted` / `no_answer_after_tokens_exhausted` | 最终轮没有产出可解析 Answer（合法出口，判 0，不算故障） |
| `task_timeout` | 180s 到点（含生成被截止截断、代码块被剩余时间钳制） |
| `action_timeout` | 单个代码块超过 15s（未触及 180s） |
| `platform_error` | 平台异常，`status=error`，附 `error` 字段 |

## 7. usage / token 口径

- `input_tokens` / `output_tokens` 全部来自本地 tokenizer 的真实计数（prompt = 渲染后的输入长度，output = 实际生成 token 数），不来自服务端 `usage` 字段——本项目不走 API。
- **拿不到就是 `null`，不填假 0**。当前唯一会写 0 的情况是 `status=error` 的 episode（`model_calls=0`，确实一次都没调用），此时以 `status`/`error` 为准。
- `budget.elapsed_seconds` 与 `episode.json` 的时间字段同源（`time.monotonic()`，起点为预算创建时刻），可比。

## 8. 旧数据（`7af057d` 及以前）的派生口径

那批记录没有 §2 的显式字段，只能用：

```text
生成停止 ≈ 最后一轮 turns.jsonl 的 budget.elapsed_seconds（含该轮代码块执行时间）
落盘     ≈ episode.json 的 wall_seconds
```

两者起点差几毫秒，所以差值是"落盘开销 + 最后一轮代码块执行时间"的上界，**不能**据此把 180s 卡到毫秒级；需要毫秒级判读时用 `fc67310` 之后的运行（或等价的 CPU 回归测试 `test_deadline_cut_records_generation_stop_and_persist_separately`）。
