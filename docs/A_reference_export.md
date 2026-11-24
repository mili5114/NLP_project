# 离线参考答案导出（A 侧源数据，C 侧校验）

课程附件 §2 要求参考答案只用于离线评分，不得进入模型输入、模型可见反馈或代码执行环境。本文件说明 A 提供的这份源数据是什么、怎么复现、C 怎么校验。

## 1. 交付物

| 文件 | 是否入库 | 内容 |
|---|---|---|
| `scripts/export_references.py` | 是 | 唯一生成入口，答案从固定上游任务对象读取 |
| `references/offline_reference_v1.manifest.json` | 是 | 43 条的 `task_id` / `split` / `answer_type` / 每条 `reference_sha256`、`content_sha256`；**不含答案原文** |
| `references/offline_reference_v1.json` | 否（`.gitignore` 明确忽略） | 评分器直接消费的离线文件，含答案原文，只存在本机/集群 |

仓库是公开的，所以答案原文不进 git：可提交的只有 hash 清单。C 用同一脚本在自己机器上生成同一份文件，按 `content_sha256` 与逐条 `reference_sha256` 校验一致性——这比传一个答案文件更能证明来源相同。

## 2. 数据来源

- 上游代码：`third_party/code-act` @ `d607f56c9cfe9e8632ebaf65dcaf2b4b7fe1c6f8`（submodule，与 manifest 里的 `team_commit` 无关，是课程固定的评测代码版本）。
- 任务名单：`configs/course/split_manifest.json`，其 sha256 写进清单（`split_manifest_sha256`），名单一改 hash 立刻变。
- 答案值：任务对象的 `expected_output`，由上游任务实现计算得出，不是人工抄写。
- 答案类型：由 `expected_output` 的真实 Python 类型决定——`int`/`float` → `numeric`，`str` → `string`。`bool`、`None`、容器、`NaN`/`Inf` 一律报错，不做猜测，也不靠“看起来像数字”判定。

## 3. 覆盖范围

| split | 条数 | 说明 |
|---|---:|---|
| DEV | 16 | A 的 DEV 基线评分用 |
| EVAL | 27 | C 的正式 EVAL 评分用 |

合计 43 条，与两个 split 的名单一一对应且唯一。当前版本 `content_sha256 = 683697256d7431d3253aacd58850ed0209d244cef460099714685f242b3118e4`。

## 4. 复现与校验（C 侧）

```bash
# 1) 生成（需要 submodule 已初始化：git submodule update --init --recursive）
python scripts/export_references.py --out references/offline_reference_v1.json

# 2) 与自己手里的清单对齐：数字与 hash 必须完全一致
python - <<'PY'
import json
m = json.load(open("references/offline_reference_v1.manifest.json", encoding="utf-8"))
r = json.load(open("references/offline_reference_v1.json", encoding="utf-8"))
assert r["content_sha256"] == m["content_sha256"], "content_sha256 不一致"
assert [(e["task_id"], e["answer_type"]) for e in r["references"]] == \
       [(e["task_id"], e["answer_type"]) for e in m["entries"]], "task 名单或类型不一致"
print("ok", m["content_sha256"], m["counts"])
PY

# 3) 直接评分（评分器自己的读取器已在生成时回读校验过）
python scripts/score.py --episodes <episode 目录或索引> \
  --references references/offline_reference_v1.json --out <scored.jsonl>
```

注意：`file_sha256` 每次生成都会变（`generated_at` 时间戳），**校验用 `content_sha256`**，它只覆盖 43 条内容。

## 5. 隔离保证（可复查）

1. **路径守卫**：`_check_out_path()` 拒绝把参考文件写进 `runs/`、`src/`、`configs/course/`、`third_party/`，防止答案混进运行记录或执行环境。
2. **不打印答案**：脚本 stdout 只输出条数、`content_sha256`、`file_sha256`，不含任何答案值。
3. **加载即静默**：任务加载复用 `src/runtime/tasks.py::load_tasks()`，它把 `Task.__init__` 的 `print_task()`（会打印标准答案）重定向到内存缓冲区并丢弃；runner 走同一条路径，所以在线日志里不会出现答案。
4. **在线记录不含答案**：`episode.json` / `turns.jsonl` 只有 `final_answer`（模型自己给的），没有 `reference_answer`；评分结果是独立文件。
5. **测试覆盖**：`tests/test_reference_export.py` 断言类型判定（含 `bool` 被拒）、路径守卫、清单不含答案原文、覆盖 43 条且顺序与名单一致。

## 6. 已知边界

- 只是“同一上游版本的派生数据”，不是新事实：上游若更新任务实现，必须新起 `offline_reference_v2`，不能覆盖 v1（旧记录按 v1 评分才可复现）。
- 数值答案按 `repr()` 输出十进制文本，评分端用 `Decimal` + 绝对误差 1e-6 比较；字符串答案原样保留，评分端负责 strip 后精确匹配。
- 本文件只覆盖 DEV/EVAL 两套名单；synthetic fixtures 不在此列（C 的 `fixtures/reference.synthetic.json` 保持不变）。
