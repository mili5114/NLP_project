# A 侧交接索引（入口）

> C 核验时按这张表走；每项都给出"文件 + 核验方式"，不需要传文件。
> 数据批次索引在 `runs/index.md`；批次内的槽位索引是 `runs/<batch>/index.jsonl`。

| 材料 | 内容 | 位置 | 怎么核 |
|---|---|---|---|
| 运行说明 | 环境准备、单任务验证、完整 DEV A/B 的准确命令、常见坑 | `docs/runbook.md` | 照命令能跑通一个任务 |
| 代码与环境 | 上游 commit `d607f56…`、基线运行 commit `de5b037`（v5 批次）、未提交状态、模型/tokenizer revision `851bf6e…`、后端、依赖锁、GPU 型号 | `docs/env_and_config.md`；证据 `configs/versions.json`、`requirements.txt`、`configs/locks/env-20261121-160506.txt`、`configs/model_provenance.json` | 与每个 `manifest.json` 的 `upstream_commit`/`team_commit`/`model` 对照 |
| 配置 | 实际生效配置；**课程设置 hash**（`faa79929…`）与**完整运行配置 hash**（`config_fingerprint`）的区别 | `docs/env_and_config.md` §3；`python scripts/config_fingerprint.py runs/dev_full_v5/DEV` | 同批 32 条 manifest 只应输出 1 个 fingerprint |
| 日志说明 | 三件套字段、180s/185s 口径（生成停止 vs 最终落盘）、最终轮标记、`termination_reason` 词表、usage 不可得时写 null | `docs/log_fields.md` | 拿任一 episode 逐字段对照 |
| 离线参考答案 | 固定上游版本的导出脚本 + 可提交的 hash 清单（答案原文不入公开仓库） | `scripts/export_references.py`、`references/offline_reference_v1.manifest.json`（`answers_in_git:false`） | 本地重跑脚本，比对 `content_sha256` |
| 资源账目 | 逐作业号、卡数、起止时间、对应批次、GPU·h 口径（含失败、取消、预热） | `docs/gpu_ledger.md` | 与 `sacct` 对账 |
| 协议验证表 | 附件 7 项逐条：已验证 / 未覆盖 / 部分，附证据位置 | `docs/protocol_verification.md` | 按表中的测试名/路径抽查 |
| 批次与结果 | 每批是什么、能否当基线；32 槽位索引；逐任务评分 | `runs/index.md`、`docs/A_dev_baseline_handoff.md`、`runs/dev_full_v5/index.jsonl`、`runs/dev_full_v5/scored.jsonl`、`runs/dev_full_v5/audit.json` | `scripts/make_run_index.py` 复核槽位；`scripts/score.py` 复核评分 |

## 三个必须知道的口径

1. **180s 是任务截止，185s 只是工程检查线**。判协议看"生成停止 ≤ 180s"，判工程看"落盘 ≤ 185s"（含停止、同步、写文件）。字段见 `docs/log_fields.md` §2。
2. **无答案 = 合法出口，判 0 分，不算故障**；`status` 只有 `error` 才是工程故障。失败、超时、预算耗尽一律保留，不重跑到成功。
3. **只有 `runs/dev_full_v5` 是基线**（`de5b037`，32 槽位单批、jobs 日志随批入库；`runs/dev_full_v4`/`dev_full_v3` 是旧版证据，v5 与 v4 的 32 个最终答案逐条相同）。`runs/dev_baselines`（首轮，签名错误）、`runs/eval_baselines`（首轮 EVAL）、`runs/dev_fix_check`（v1）、`runs/dev_fix_check_v2`（v2）、`runs/repro_check` 都是诊断/验证材料，**不混入基线**。

## 已知限制（写给报告 Limitations）

- 执行环境无硬沙箱：同进程 Python，工具函数 `__globals__` 理论上可回溯任务模块；靠 contract + 全量轨迹扫描把关（`scripts/check_answer_isolation.py`）。
- 真实样例未覆盖 180s 到点截断与 16384 上下文上限（`docs/protocol_verification.md` 第 2 表）。
- **工具预算耗尽后没有立即进最终轮**（课程附件要求"Move to the final-answer turn when the tool budget is exhausted"）：v4 里 A `multi_city_business_trip` 在 32 次执行用完后仍继续 4 个交互轮、16 次全被拦，直到轮次耗尽才进最终轮。影响 1/32 槽位（该题本就判错）。细节与修法见 `docs/A_dev_baseline_handoff.md` §7；要不要在 EVAL 前修由 B/C 定。
- v4 时代审计报的 2 个 blocked 计数 error 已由 C 在 `c/real-log-audit`（PR #3）修正口径解决；v5 用修正后的审计 **PASS（0 error / 0 warning）**，见 `docs/A_dev_baseline_handoff.md` §5。
- v3 批次曾有两个同 `run_id` 的作业并发（14100663 / 14100664）写坏 1 个槽位（后由 14100878 单槽补跑修好）；v4 是单批写到底，不存在拼接。
