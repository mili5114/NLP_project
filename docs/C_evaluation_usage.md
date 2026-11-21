# 成员 C：离线评测工具使用说明

本文件描述 `c/evaluation-tools` 分支上**已实现并可运行**的工具。所有命令在仓库根目录执行，不需要手动设置 `PYTHONPATH`。

## 1. 环境与依赖

- 评分、审计、汇总：Python 3.10+ 标准库即可，无第三方依赖。
- 仅 `scripts/plot_results.py` 需要 `matplotlib`（见 `requirements-evaluation.txt`）。本机验证使用 `C:/Users/qzheng/.workbuddy/binaries/python/envs/default/Scripts/python.exe`（matplotlib 3.11.2）。
- 不下载模型，不运行 runner，不连接 agent。参考文件只读离线 JSON。

## 2. 输入格式

### 2.1 离线参考答案：`fixtures/reference.synthetic.json` 结构

```json
{
  "synthetic": true,
  "offline_only": true,
  "references": [
    {"task_id": "synthetic/example_numeric", "answer_type": "numeric", "reference": "42"}
  ]
}
```

- `answer_type` 只接受 `numeric` 或 `string`，**由离线参考数据提供**，不根据预测猜测。
- 每个 `task_id` 必须唯一；重复、缺失、未知类型、文件损坏都会以非零退出并明确报错，绝不当成普通答错。
- 参考答案与任何 `expected_success` 只存在于离线文件；评分器不会把它们写进 scored 输出，也不会送进运行器或反馈。

### 2.2 episode 输入

`--episodes` 接受三种形式：

1. 单个 episode JSON（如 `fixtures/episode.synthetic.json`）；
2. JSONL 索引，每行 `{"episode_path": "episodes/xxx.json"}`，**相对路径按索引文件所在目录解析**；也允许行内直接是 episode 对象；
3. 目录：扫描其中所有 `*.json`，只把可识别为 episode 的文件纳入，并保存精确文件清单，避免混入旧运行。

episode 字段沿用 `docs/interfaces.md` 第 3 节（`task_id`、`split`、`condition`、`final_answer`、`input_tokens`、`output_tokens`、`model_calls`、`trajectory_path`、`config_sha256` 等）。

### 2.3 turns.jsonl 合成最小结构（重要）

`docs/interfaces.md` 只规定了 turns 的语义，没有逐字段 schema。下面这套最小结构是**C 为合成测试自定义的**，不是 A 已承诺的最终字段；真实日志到达时通过 `src/evaluation/turns_reader.py` 这一个适配层做一次明确映射，不静默兼容各种拼写、不把缺失 usage 填成 0。

每行一次模型调用（**最终回答调用也写一行**）：

```json
{
  "turn_index": 1,
  "is_final": false,
  "messages": [{"role": "user", "content": "..."}],
  "generation_settings": {"max_tokens": 384},
  "raw_model_text": "Action: ...",
  "parsed_action": "...",
  "action": "python",
  "python_output": "...",
  "events": [{"index": 1, "tool": "...", "execution_status": "ok"}],
  "feedback": "模型可见反馈文本",
  "feedback_metadata": {},
  "input_tokens": 100,
  "output_tokens": 10,
  "wall_seconds": 0.5
}
```

`is_final: true` 标记最终回答调用。usage 缺失会被审计明确记录，不填 0。

## 3. 命令

```bash
# 生成/重新生成合成 fixtures（可重复执行）
python scripts/make_synthetic_fixtures.py

# 1) 评分（A/B 可直接复用这条形式）
python scripts/score.py \
  --episodes fixtures/episode.synthetic.json \
  --references fixtures/reference.synthetic.json \
  --out results/synthetic/scored.jsonl \
  --allow-synthetic

# 2) 审计（正式 EVAL 用 --split EVAL --conditions A B C D）
python scripts/audit_results.py \
  --episodes fixtures/evaluation/index.jsonl \
  --split SYNTHETIC --conditions A B C D \
  --allow-synthetic --synthetic-tasks fixtures/evaluation/tasks.json \
  --expected-config-sha synthetic-config-sha-placeholder \
  --out results/synthetic/audit.json

# 3) 汇总
python scripts/summarize.py \
  --scored results/synthetic/scored_all.jsonl \
  --audit results/synthetic/audit.json \
  --split SYNTHETIC --conditions A B C D \
  --allow-synthetic --synthetic-tasks fixtures/evaluation/tasks.json \
  --out-dir results/synthetic

# 4) 图表（需要 matplotlib）
python scripts/plot_results.py \
  --summary results/synthetic/summary.json \
  --out-dir results/synthetic/plots --allow-synthetic

# 测试
python -m unittest discover -s tests -v
```

正式模式没有 `--allow-synthetic`；任何 synthetic episode 或 synthetic 参考文件都会被拒绝（退出码 2）。合成审计必须用 `--synthetic-tasks` 给显式任务清单，synthetic 任务不会写入官方 `split_manifest.json`。

## 4. 评分语义

- `numeric`：`Decimal` 精确解析，预测和参考都必须是有限数，`|pred-ref| <= Decimal('0.000001')` 判正确；不用 float 做比较，动态提高 Decimal 精度以覆盖高精度和大数。NaN/Infinity/无法解析的**预测**记为失败；同样问题出现在**参考**则是数据错误。
- `string`：仅 `strip()` 首尾空白后精确匹配；不改大小写、不动内部空格、不去标点。
- `final_answer` 为 null：记 `success=false`、`scoring_reason="no_answer"`，保留原 `termination_reason`，不丢弃样本。
- 评分器的输入 episode 不被修改；输出是独立 scored JSONL，只新增 `success` / `scoring_reason` / `answer_type`，不含参考答案。

## 5. 审计覆盖

从 `configs/course/split_manifest.json` 读任务名单（正式 EVAL 预期 27 × 4 = 108 槽位），检查：缺失、重复、未知任务、错误 split、非请求 condition、trajectory 文件存在性与 JSONL 合法性、模型调用数、逐轮 tokens 与 episode 总量一致、最终回答调用已计入、synthetic 污染、config hash / 版本一致性，以及 `runtime_settings.json` 中可核验的预算（轮次、反馈字符数、逐轮/总 token、每代码块与每任务工具次数、单任务耗时）。

「有记录但模型失败」和「记录缺失」分开列出：前者在 `recorded_failures`，后者在 `missing_slots`，后者使状态变为 FAIL/INCOMPLETE，不会用缩小分母掩盖。审计失败时仍写报告文件并返回非零退出码。

## 6. 统计口径

- 逐任务表 `per_task.csv`：成功、终止原因、tokens、调用数、耗时、run_id、证据路径。
- 主表 `condition_summary.csv`：`N_expected`、`N_recorded`、`N_scored`、`success_count`、`success_rate`、各类均值。成功率分母是**预期任务数**，失败样本全部计入。
- tokens 先汇总每题全部模型调用，再对任务求均值；缺失 usage 不填 0，而是从该项均值中排除并记 `n_with_usage` / `n_with_output_usage`。
- 数据不完整时主表标 `INCOMPLETE — NOT FINAL RESULTS`，不输出可被误用为正式结论的完整结果。
- `C vs D` 是筛选规则的归因比较；`C vs B` 同时改变排序和筛选，只描述完整方案差异，不单独归因于筛选。两种解释都写进配对表和 `summary.json`。

## 7. 产物标记

`results/synthetic/` 下的所有表格与图表都带 `SYNTHETIC — NOT EXPERIMENTAL RESULTS`。正式产物会在 A 的日志和 B 的冻结包到位后写到 `results/`，并由审计状态决定是否有完整主表。
