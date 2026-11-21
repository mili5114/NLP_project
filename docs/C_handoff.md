# 交接给 A / B：如何使用 C 的离线评分器

评分器已实现并在本机验证通过（56 个单元测试全绿；合成 12 槽位端到端跑通）。A/B 不需要等图表模块，现在就可以给自己的 DEV runs 评分。

## 1. 安装

核心评分无需第三方依赖：

```bash
python scripts/score.py --help
```

## 2. 一条可直接使用的评分命令

A/B 在仓库根目录执行，把路径换成自己的 DEV run 索引和离线参考文件：

```bash
python scripts/score.py \
  --episodes runs/dev_baselines/<your_run>/index.jsonl \
  --references <offline_reference.json> \
  --out results/<your_run>/scored.jsonl
```

- 正式 DEV 数据不要加 `--allow-synthetic`；一旦混入 synthetic 记录会直接报错退出。
- `<offline_reference.json>` 结构见 `docs/C_evaluation_usage.md` 第 2.1 节；A 负责提供固定版本的参考导出或源数据说明，C 负责校验评分端。
- `--episodes` 也可直接指向单个 episode JSON 或 episode 目录。

评分器**只读取** episode 中的 `final_answer`，不重新解析轨迹挑答案，也不会把参考答案送入 runner 或反馈。输出是独立的 scored JSONL，在线原始日志不会被修改。

## 3. 错误行为（便于定位）

退出码 2，stderr 带 `ERROR:`：

- 参考缺失 / 重复 / `answer_type` 未知 / JSON 损坏 → 数据错误；
- episode 找不到对应 `task_id` 的参考 → 明确报出 task_id 和来源；
- 未加 `--allow-synthetic` 却传入 synthetic → 拒绝；
- 参数缺失 → argparse 非零退出。

普通答错、无答案、NaN/Infinity 预测都是 `success=false` 的正常评分结果，不是报错。注意：即使无答案，参考值类型不合法仍会报数据错误，不会被当成模型答错。

## 3.1 审计/汇总对交接数据的要求

- 每份审计必须基于同一次输入；`audit.json` 带 `input_fingerprint` 和槽位集合。`summarize.py` 会重算指纹与槽位、run/config 身份，旧审计配新数据会被标为 INCOMPLETE 并以退出码 2 拒绝当作完整结果。
- 正式审计必须提供 code commit、model revision 和**按条件**的 config hash（`--condition-config-sha A=<sha> ...` 或 `--condition-config-sha-file`）。A/B/C/D 的完整配置 hash 允许不同，逐条件核对。
- `success` 必须是布尔；评分文件出现重复槽位会被检出并先去重，成功率封顶 1.0，不会出现 >100%。

## 4. A/B 各自还要提供什么

- **A**：真实 episode + turns + manifest 样例和字段说明。当前 `src/evaluation/turns_reader.py` 里的字段是 C 的合成测试结构，**不是 A 的最终 schema**；真实日志到达后由 C 在适配层做一次显式映射，若有字段改动请提前告知。
- **B**：四条件冻结配置、`config_sha256`、模型/tokenizer revision、团队代码 commit、课程附件 hash；正式审计会逐项核对。
- **A/B**：各自 DEV run 索引与 GPU/资源账目，C 只汇总，不接管重跑。

## 5. 缺陷反馈格式

请在 Issue 里给出：仓库 commit、分支、完整命令、输入文件路径、期望行为、实际输出（含 `ERROR:` 行或审计 JSON 中的 `code` / `task_id` / `condition` / `owner`）。缺陷发回原 Owner：在线/日志字段归 A，冻结配置归 B，离线工具归 C。
