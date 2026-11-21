# 个人贡献记录 — 成员 C（郑启丹 QidanZheng）

分支：`c/evaluation-tools`（从 `origin/main` 创建，未合并默认分支）。

## 1. 本轮实际完成的代码

| 文件 | 内容 |
|---|---|
| `src/evaluation/scoring.py` | `score_episode`：Decimal 数值评分、字符串 strip 后精确匹配、无答案失败、参考数据决定 answer_type、数据错误明确抛出 |
| `src/evaluation/io.py` | 参考文件/episode/JSONL 索引/目录读取，synthetic 门控，确定性 JSONL 写出 |
| `src/evaluation/errors.py` | 数据错误与输入错误异常层次 |
| `src/evaluation/turns_reader.py` | turns.jsonl 独立读取适配层；合成最小 schema 文档化，不冒充 A 的最终字段 |
| `src/evaluation/audit.py` | 从官方 manifest 读任务名单；槽位完整性、轨迹/token/最终调用核验、synthetic 污染、hash 一致、课程预算检查 |
| `src/evaluation/aggregation.py` | 逐任务表、条件主表、C vs B / C vs D 配对；缺失 usage 不填 0，不完整数据标 INCOMPLETE |
| `src/evaluation/plots.py` | 成功率、token 成本、配对结局图；PNG/PDF，标题和图中标注合成 |
| `scripts/score.py` / `audit_results.py` / `summarize.py` / `plot_results.py` | 四个 CLI，仓库根目录直接运行，无需设置 PYTHONPATH |
| `scripts/make_synthetic_fixtures.py` | 可重复生成的 12 槽位合成数据与轨迹 |
| `tests/test_scoring.py` / `test_audit.py` / `test_aggregation.py` | 35 个单元测试 |
| `docs/C_evaluation_usage.md` / `C_handoff.md` / `C_eval_readiness.md` / `contributions/C.md` | 使用、交接、就绪度与个人贡献文档 |
| `.gitignore` / `requirements-evaluation.txt` | 忽略环境与原始日志；仅图表依赖 matplotlib |

## 2. 关键决策

- 数值比较全程 `Decimal`，按操作数指数动态提高精度，避免默认 28 位精度在高精度/大数边界误判；不经过 float。
- 参考里的 NaN/Infinity/未知类型是数据错误；预测里的同类问题是保留的失败样本，二者严格区分。
- 「有记录但模型失败」与「记录缺失」分列；缺失不会缩小成功率分母，审计失败仍写报告并非零退出。
- tokens 先按任务汇总全部调用再对任务求均值；缺失 usage 从该项均值中排除，不补 0。
- `C vs D` 才是筛选归因；`C vs B` 同时改变排序与筛选，报告中明确写清不能全部归因于筛选。
- 合成数据默认拒绝，只能显式 `--allow-synthetic` 使用；合成任务用独立清单，不写入官方 manifest；所有产物带合成横幅。
- 只实现 C 的离线工具，没有重建 runner、没有实现反馈条件、没有替 A/B 跑 DEV、没有下载模型或运行正式 EVAL。

## 3. 实际运行的验证

```bash
python -m unittest discover -s tests -v          # Ran 35 tests ... OK
python scripts/make_synthetic_fixtures.py        # wrote 12 synthetic episodes + trajectories
python scripts/score.py --episodes fixtures/episode.synthetic.json \
  --references fixtures/reference.synthetic.json \
  --out results/synthetic/scored.jsonl --allow-synthetic
# scored=1 success=1 synthetic=True
python scripts/score.py --episodes fixtures/evaluation/index.jsonl \
  --references fixtures/evaluation/reference.json \
  --out results/synthetic/scored_all.jsonl --allow-synthetic
# scored=12 success=6 synthetic=True
python scripts/audit_results.py --episodes fixtures/evaluation/index.jsonl \
  --split SYNTHETIC --conditions A B C D --allow-synthetic \
  --synthetic-tasks fixtures/evaluation/tasks.json \
  --expected-config-sha synthetic-config-sha-placeholder \
  --out results/synthetic/audit.json
# audit status=PASS expected=12 recorded=12 errors=0 warnings=0 synthetic=True
python scripts/summarize.py --scored results/synthetic/scored_all.jsonl \
  --audit results/synthetic/audit.json --split SYNTHETIC --conditions A B C D \
  --allow-synthetic --synthetic-tasks fixtures/evaluation/tasks.json \
  --out-dir results/synthetic
# A:2/3  B:1/3  C:2/3  D:1/3；C 平均 input=200 / output=13
python scripts/plot_results.py --summary results/synthetic/summary.json \
  --out-dir results/synthetic/plots --allow-synthetic   # 6 个图表文件
```

正式模式（不加 `--allow-synthetic`）对同一合成输入返回退出码 2，确认门控生效。

## 4. 本轮边界

所有 `results/synthetic/` 下的表格与图都是合成演示，**不是实验结果**。正式 EVAL 尚缺 A 的平台/真实日志/参考导出与 B 的冻结包，详见 `docs/C_eval_readiness.md`。本轮未开展真实推理、未修改方法、未编造结果。
