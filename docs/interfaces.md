# 开工接口约定 v1

状态：已提供可供三人并行开发的接口与合成样例；尚未实现 CodeAct 平台、模型连接或评分器。模型、预算和四条件算法以课程附件及研究方案为准。

## 1. 目录与唯一所有者

- A：`src/runtime/`、`src/records/`、`src/feedback/baselines.py`，在线轨迹格式和工具事件观察器。
- B：`src/feedback/selective.py`、`src/feedback/renderers.py`、`configs/conditions/`、`configs/frozen/`。
- C：`src/evaluation/`、`scripts/score.py`、`scripts/audit_results.py`、`scripts/summarize.py`、`results/`。
- 课程原始设置：`configs/course/`。不得在模块中另写一份任务名单或限制。
- 首次接真实上游实现若发现接口需要适配，由对应 Owner 修改内部适配层；外部字段有必要改动时用版本号记录一次，不让三人反复猜测。

## 2. 反馈插件：A 调用，B 实现

```python
build_feedback(*, python_output: str, events: list[dict],
               condition: str, settings: dict) -> dict
```

condition 只取 `A/B/C/D`。settings 从课程 runtime_settings 与方法配置组合；所有反馈条件共用相同课程上限。

返回值：`{"text": str, "metadata": dict}`。text 是实际送入下一轮 messages 的完整反馈，长度不超过 2000 字符。metadata 至少包含：`selected_event_indices`、`omitted_event_indices`、`truncated`、`feedback_chars`、`rule_trigger_count`。A 保存 metadata 但不把它额外发送给模型。

输入不含标准答案、评分、task 定义对象或测试集表现。函数不得再次执行工具、改变事件对象或改写解释器状态。A 实现 A/B；B 实现 C/D，统一入口由 A 按条件 dispatch。

工具事件最小字段：`index`（块内从1开始）、`tool`、`args_repr`、`kwargs_repr`、`execution_status`（ok/error/blocked）、`result_repr`、`error_repr`、`elapsed_seconds`。result/error 中不适用项为 null。blocked 表示工具未执行，不是正常返回；真实调用尝试顺序必须保留。观察器完整证据与模型显示表示分开保存。

## 3. 运行记录：A 写入，C 读取

每个 episode 是一个 task × condition 的独立运行。路径使用安全 slug，原始 task_id 保留在字段里。

- `manifest.json`：schema_version、run_id、split、condition、seed、模型/tokenizer revision、上游和团队代码版本、配置 hash、附件 hash、后端/依赖/GPU、开始结束时间和任务列表。
- `turns.jsonl`：每行一次模型调用，包含实际 messages、生成设置、原始模型文本、解析结果、action、工具 events、Python 原始输出、模型可见反馈、feedback_metadata、真实输入/输出 tokens、耗时、预算余量。最终回答调用也写一行。
- `episode.json`：schema_version、synthetic、run_id、task_id、split、condition、status、termination_reason、final_answer、input_tokens、output_tokens、model_calls、tool_attempts_executed、tool_attempts_blocked、wall_seconds、trajectory_path、config_sha256。

在线记录没有 reference_answer/success。无答案时 final_answer 为 null，仍保留 episode。配置 hash、版本和真实 token 统计必须来自实际运行，不能把 fixture 的数字复制到正式记录。

## 4. 离线评分：C 提供，A/B 自行调用

```python
score_episode(episode: dict, *, reference: str,
              answer_type: str) -> dict
```

answer_type 由固定上游任务的答案语义提供，不靠预测是否像数字决定。只接受 `numeric/string`；未识别类型报错。返回 episode 原始字段加 `success` 和 `scoring_reason`，写入单独 scored 文件。reference 不进入在线记录、feedback 或执行环境。

目标命令接口（尚待 C 实现）：`score --episodes <index> --references <offline-source> --out <scored-file>`；`audit_results --episodes <index> --split DEV --conditions A B`。具体 Python 入口由 C 写入使用文档，不能假设现在即可执行。

## 5. 已有样例与边界

`fixtures/feedback_input.json` 用于 B 的筛选开发；`fixtures/episode.synthetic.json` 用于 C 的汇总开发；`fixtures/reference.synthetic.json` 只供离线评分 fixture 使用。全部标 synthetic，只验证数据格式，不用于课程结果或候选选择。

A 可先用 `text=python_output` 的 stub 完成平台。B 可不依赖 GPU 开发 renderer。C 可不依赖真实日志开发 scorer。DEV 实验前，A 将真实日志替换 fixture，并验证字段与真实调用一致。
