# C：正式 EVAL 执行与验收手册

状态：准备稿，未启动正式 EVAL。更新于 2026-11-25，依据远端 `5a757d4` 与 C 审计 `25d6529`。Owner：成员 C。课程设置以 `configs/course/` 为准，不能把本文当成新的实验预算。

## 1. 现在完成、冻结后填入

| 关口 | 输入 / 判断 | 责任 |
|---|---|---|
| 运行协议 | 工具尝试预算耗尽后下一次调用 final-only；时间/上下文硬停止优先；C 审计通过修复版 DEV | A 修复，C 验收 |
| 方法选择 | 最多 3 个 DEV 候选；选择记录、C/D 实现及消融；不利用旧 EVAL 诊断结果选方法 | B |
| 冻结包 | 一个四条件共用的代码 commit；模型/tokenizer/upstream/后端锁；每条件完整配置及 hash；4 条经 DEV 验证的运行命令；已知限制 | B 交付，C 接收 |
| 执行环境 | GPU 账号可用、模型可读、环境锁一致、独立执行工作目录 clean，且 HEAD 是冻结 commit | C |
| 离线参考 | 内容 hash 与公开清单一致；原文只留离线评分环境 | C |

当前 `src/feedback/dispatcher.py` 在缺少方法实现时拒绝 C/D。**本手册不承诺当前 main 已能启动四条件。** 不使用旧 v4 或首轮 EVAL 代替修复后冻结版本。

冻结交接只需在 B 的冻结记录填一次，下表是 C 的接收清单，不另要求第二份相同资料：

| 字段 | 待填写 |
|---|---|
| frozen code commit | 待 B 冻结 |
| freeze record 路径 / 时间 | 待 B 冻结 |
| A/B/C/D 实际生效配置路径与完整 hash | 待 B 冻结 |
| episode.config_sha256 的口径 | 目前为课程 runtime_settings 文件 hash；若仍如此，另核验完整配置 hash，不冒充完整配置审计 |
| 四条件准确启动命令与后端 | 待 B 交付并在 DEV 验证 |
| DEV 选择记录与协议验收报告 | 待新版 DEV |
| 新批次目录 | `runs/eval/<唯一批次名>/`，执行前确定 |
| 资源账目和作业日志位置 | 执行前确定 |

冻结后先核验交接，不通过则停在此处。不要在 EVAL 上调参或试接 C/D。

## 2. 执行规则

1. 从固定 `split_manifest.json` 读取全部 27 个 EVAL task，四条件 108 唯一槽位。每条件每任务一次计划运行，首个可解析 Answer 即结束。
2. 在 GPU 的独立冻结 checkout 运行，不在数据拉取/写报告的 checkout 上启动作业。提交前记录 HEAD、dirty 状态、配置和作业命令。文档/数据提交不会改变已冻结执行目录。
3. 使用 B 验证过的四条命令。现有平台参数为 `python -m src.runtime.runner --split EVAL --condition <A|B|C|D> --model-dir <MODEL_DIR> --runs-root <新批次根目录>`；方法额外参数以冻结包为准，不能猜测。
4. 不设置 pilot 的 `--limit`，不继承旧 `TASKS` 环境变量。使用 Slurm 时 `SPLIT=EVAL`、每作业一个 COND；多任务不要放进逗号分隔的 `--export=`。
5. 同一 task×condition 不允许两作业并发写同一目录。同批不同 condition 可并行；卡型、后端和实际配置按冻结包统一，是否并发由可用 GPU 决定。
6. 每个任务保存 manifest/episode/turns；保留失败、无答案、超时、预算耗尽。记录作业号、卡数、起止和实际运行时长，含加载/预热成本。
7. 作业结束后确认文件落盘，再打包取回。私有答案不能打包进在线环境，不能公开上传；公开原始轨迹前检查密钥/私有路径等。

故障处理：排队和有效运行分开记。若基础设施故障造成文件缺失/混写，先归档原目录和故障日志、明确恢复原因与槽位，再在新目录恢复；不以答案错误为重跑理由。若发现共享运行时/方法缺陷，暂停正式结论，记录新版本与重冻决定，按影响范围重做一致比较；不拼接新旧协议。

## 3. 本地验收和离线结果命令

以下在仓库根目录的 PowerShell 执行。变量是待填参数；占位符保护会拒绝直接执行。评分器只读取冻结后新批次。不要把最新文档 HEAD 当运行版本。

```powershell
$batch = 'runs/eval/REPLACE_BATCH'
$out = 'results/REPLACE_BATCH'
$runCommit = 'REPLACE_FROZEN_COMMIT'
$configMap = 'REPLACE_CONDITION_HASH_MAP_JSON'
if (@($batch,$out,$runCommit,$configMap) -match 'REPLACE_') { throw '先按冻结包填写参数' }
$modelRevision = '851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a'
function Invoke-CheckedPython {
    & python @args
    if ($LASTEXITCODE -ne 0) { throw "Python step failed (exit $LASTEXITCODE); keep evidence and stop" }
}

# 必须先人工对照冻结配置、完整配置 hash 与各 manifest，不能只对课程设置 hash。
Invoke-CheckedPython scripts/make_run_index.py $batch --split EVAL --conditions A B C D
Invoke-CheckedPython scripts/check_run_records.py $batch
Invoke-CheckedPython scripts/check_budget_accounting.py --runs "$batch/EVAL"
Invoke-CheckedPython scripts/check_answer_isolation.py --runs $batch
Invoke-CheckedPython scripts/audit_results.py --episodes "$batch/index.jsonl" --split EVAL --conditions A B C D --out "$out/audit.json" --expected-code-commit $runCommit --expected-model-revision $modelRevision --condition-config-sha-file $configMap
Invoke-CheckedPython scripts/score.py --episodes "$batch/index.jsonl" --references references/offline_reference_v1.json --out "$out/scored.jsonl"
Invoke-CheckedPython scripts/summarize.py --scored "$out/scored.jsonl" --audit "$out/audit.json" --split EVAL --conditions A B C D --out-dir $out
Invoke-CheckedPython scripts/plot_results.py --summary "$out/summary.json" --out-dir "$out/plots"
```

`$configMap` 是 JSON condition→hash 映射，值必须与冻结时声明的 **episode.config_sha256 口径**一致。完整配置比对作为独立证据保留。`config_fingerprint.py` 当前把 condition 排除且要求全目录单指纹；C/D 配置合法不同时，不要把四条件整批“必须同 hash”作为要求，应逐条件运行并对照各自冻结值。

索引器会把异 split/condition 记录也写入索引；不能只看其 PASS，后续严格审计必须继续通过。使用纯净批次目录，避免混入旧记录。

参考答案首次生成见 `A_reference_export.md`。已存在则先验证 content/逐条 hash，不覆盖。结构扫描不证明执行环境硬隔离。真实时间边界未触发时如实标未覆盖，不用容差替代 180 秒课程预算。

## 4. 验收交付

- 原始 108 槽位、批次索引、来源/配置/版本清单、作业日志和资源账目。
- `audit.json` PASS（同时复核 warnings 与未覆盖项）、`scored.jsonl`、`per_task.csv`、`condition_summary.csv`、`summary.json`。
- `paired_C_vs_B.csv`、`paired_C_vs_D.csv`、图表源数据与 PNG/PDF。
- 5–10 个配对案例，成功和退步均保留，定位到 task/condition/turn。
- C 结果章节、poster/demo 成品、贡献记录。最终上传格式按课程通知；不对未确认的展示时长或录屏形式作承诺。

合格判定：108 槽位、版本/配置和协议检查通过，缺 usage 不填 0、失败不删除，汇总 binding complete。任一关失败，保留 INCOMPLETE，不输出最终方法优劣结论。
