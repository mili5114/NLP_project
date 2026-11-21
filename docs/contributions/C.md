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
| `tests/test_scoring.py` / `test_audit.py` / `test_aggregation.py` | 56 个单元测试 |
| `docs/C_evaluation_usage.md` / `C_handoff.md` / `C_eval_readiness.md` / `contributions/C.md` | 使用、交接、就绪度与个人贡献文档 |
| `.gitignore` / `requirements-evaluation.txt` | 忽略环境与原始日志；仅图表依赖 matplotlib |

## 2. 关键决策

- 数值比较全程 `Decimal`，按操作数指数动态提高精度，避免默认 28 位精度在高精度/大数边界误判；不经过 float。
- 参考里的 NaN/Infinity/未知类型是数据错误；预测里的同类问题是保留的失败样本，二者严格区分。
- 「有记录但模型失败」与「记录缺失」分列；缺失不会缩小成功率分母，审计失败仍写报告并非零退出。
- tokens 先按任务汇总全部调用再对任务求均值；缺失 usage 从该项均值中排除，不补 0。
- `C vs D` 才是筛选归因；`C vs B` 同时改变排序与筛选，报告中明确写清不能全部归因于筛选。
- 合成数据默认拒绝，只能显式 `--allow-synthetic` 使用；合成任务用独立清单，不写入官方 manifest；所有产物带合成横幅。
- 汇总不盲信 audit JSON：用输入指纹、唯一槽位集合、run/config 身份把评分文件重新绑定到审计；旧审计配新数据判 INCOMPLETE。
- 最终 Answer 与 final-only 轮是两个概念：交互轮产出 Answer 仍按 384 上限，只有预算后追加的 final-only 轮用 128 上限。
- 正式审计强制 version/config 检查：缺 code commit、model revision 或每条件 config hash 即不通过；config hash 按条件核对，不要求四条件相同。
- 参考值在无答案提前返回之前校验，避免把数据错误伪装成模型答错。
- 只实现 C 的离线工具，没有重建 runner、没有实现反馈条件、没有替 A/B 跑 DEV、没有下载模型或运行正式 EVAL。

## 3. 实际运行的验证

```bash
python -m unittest discover -s tests -v          # Ran 56 tests ... OK
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
  --condition-config-sha-file fixtures/evaluation/condition_config_shas.json \
  --out results/synthetic/audit.json
# audit status=PASS expected=12 recorded=12 errors=0 warnings=0 synthetic=True
python scripts/summarize.py --scored results/synthetic/scored_all.jsonl \
  --audit results/synthetic/audit.json --split SYNTHETIC --conditions A B C D \
  --allow-synthetic --synthetic-tasks fixtures/evaluation/tasks.json \
  --out-dir results/synthetic
# A:2/3 B:1/3 C:2/3 D:1/3；C 平均 input=126.6667 / output=10.3333；effective_complete=True
python scripts/plot_results.py --summary results/synthetic/summary.json \
  --out-dir results/synthetic/plots --allow-synthetic   # 6 个图表文件
```

正式模式（不加 `--allow-synthetic`）对同一合成输入返回退出码 2，确认门控生效。旧审计配新数据时 `summarize.py` 返回 2、状态 INCOMPLETE、`binding.problems` 含 `audit_fingerprint_mismatch`。

## 4. Review 后修复（第二轮）

| 问题 | 复现/回归测试 | 修复 |
|---|---|---|
| 汇总盲信 audit.complete | `BindingTests.test_stale_audit_with_new_data_is_incomplete`、`test_audit_without_fingerprint_is_incomplete`、`test_non_boolean_success_is_incomplete`、`test_duplicate_slot_cannot_exceed_100_percent`、`test_run_identity_mismatch_detected`、`test_config_identity_mismatch_detected` | `validate_binding` 用输入指纹、槽位集合、run/config 身份重绑定；重查重复/缺失/split/conditions/布尔 success；去重并把成功率封顶 1.0 |
| 最终 Answer 与 final-only 轮混淆 | `FinalAnswerSemanticsTests` 6 项、`TurnsReaderTests.test_usage_separates_the_two_final_concepts`、`test_final_only_turn_is_distinct` | 拆成 `produced_final_answer`（384 上限）与 `is_final_answer_turn`（128 上限、最后一行、无工具）；分别记录 |
| 正式版本检查可被跳过 | `FormalVersionTests` 3 项、`AuditTests.test_per_condition_hashes_may_differ`、`test_config_hash_mismatch_detected` | 正式审计强制 code commit/model revision/config hash；缺字段记错误；config hash 按 condition 核对，允许四条件不同 |
| 无答案时不校验参考值 | `NumericScoringTests.test_no_answer_still_validates_reference` | 参考值类型校验移到 null 提前返回之前 |

旧代码复现（issue 4）：在上一提交 `8c34964` 的 `scoring.py` 上，`score_episode({"final_answer": None}, reference="NaN", answer_type="numeric")` 返回 `success=False, no_answer` 而不报错；修复后抛 `DataError`。

## 5. 本轮边界

所有 `results/synthetic/` 下的表格与图都是合成演示，**不是实验结果**。正式 EVAL 尚缺 A 的平台/真实日志/参考导出与 B 的冻结包，详见 `docs/C_eval_readiness.md`。本轮未开展真实推理、未修改方法、未编造结果。
