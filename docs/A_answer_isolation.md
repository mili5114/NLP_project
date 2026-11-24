# 在线答案隔离证据（A 侧）

C 的就绪度清单要求 A 提供“参考答案与任务定义未进入模型输入/代码环境的证据”。这份文件把证据链拆成四段，每段都能被独立复查。

## 1. 结论

| 会被谁看到 | 是否含参考答案 | 依据 |
|---|---|---|
| 模型 system prompt | 否 | 由 `task.get_prompt()` + `initial_contract` 拼成，只含工具描述与 instruction，不读 `expected_output` |
| 模型可见反馈 | 否 | A/B 反馈只由 `python_output` 与工具事件渲染；`build_feedback()` 入参不含答案 |
| 代码执行环境 | 否 | REPL 只暴露 `task._ns`（工具函数），任务对象与答案不进命名空间 |
| 在线记录（`episode.json` / `turns.jsonl` / `manifest.json`） | 否 | 写入端显式白名单，`reference_answer` / `expected_output` / `success` 一律不写 |
| 离线评分文件 | 是（设计如此） | `references/offline_reference_v1.json`，`offline_only: true`，`gitignore` 排除，只喂 scorer |

## 2. 机制（可点开代码核对）

1. **答案打印被吞掉**：上游 `Task.__init__` 会调用 `print_task()`，把 `Expected Output: ...` 打到 stdout。`src/runtime/tasks.py::load_tasks()` 用 `contextlib.redirect_stdout/redirect_stderr` 把整段重定向到内存 `StringIO`，返回前丢弃，不落盘、不写日志。
2. **prompt 不含答案**：`src/runtime/runner.py::build_system_prompt()` 只有两个来源——`task.get_prompt(action_mode())`（工具列表 + 签名 + instruction）与课程附件的 `initial_contract`。
3. **执行环境只暴露工具**：`Task.reset()` 里 `self._ns = {tool_name: tool.function}`，runner 只用 `_ns` 建 REPL 命名空间；任务对象本身不进入解释器。
4. **记录写入白名单**：`src/records/writer.py` 按固定字段写 `episode.json` / `manifest.json` / `turns.jsonl`，注释里明确 `reference_answer` / `success` 不写。
5. **参考文件只能在离线位置**：`scripts/export_references.py::_check_out_path()` 拒绝写进 `runs/`、`src/`、`configs/course/`、`third_party/`；答案原文被 `.gitignore` 排除，公开仓库只有 hash 清单（见 `docs/A_reference_export.md`）。

## 3. 可执行证据

```bash
# 1) 43 个任务的 prompt 逐个渲染，断言不含 "Expected Output:" / expected_output / is_correct
python -m unittest tests.test_answer_isolation -v

# 2) 扫全部真实运行记录里的答案痕迹（字段名与打印标记），命中即非零退出
python scripts/check_answer_isolation.py
```

最近一次实际运行（2026-11-24，包含首轮 86 条基线、fix-check 样例与 v2）：

```
scanned 279 files in 93 episode dirs
PASS: no reference-answer trace in online records
```

`tests/test_runtime_cpu.py::test_no_reference_leak` 另外从“跑完一个 episode 后逐个文件读”这个角度断言记录里没有 `expected_output` / `Expected Output` / `is_correct`。

## 4. 边界（别把它当成比它更强的保证）

- **单字符答案会与任务描述里的数字重合**：例如答案 `4` 或 `3` 会自然出现在价格文本中。所以不能用“答案值是否出现”来自动判定泄漏，本文件与测试都只依赖“harness 是否追加了答案”这一可判定事实。
- **扫描器是标记式的**：它抓 `Expected Output:`、`expected_output`、`is_correct`、`reference_answer`。如果以后有人新增别的字段名去存答案，扫描器不会自己变聪明——这时应改 `MARKERS` 并加测试，而不是放宽检查。
- **模型自己猜对不算泄漏**：`episode.json` 的 `final_answer` 是模型输出，可能恰好正确；正确性只在离线评分阶段用参考文件判定。
