# NLP_project

AIAA 4051 Project 14 — Execution Feedback and Interaction Efficiency in CodeAct Agents.

**三人分工与认领，先看 [TEAM_QUICKSTART.md](TEAM_QUICKSTART.md)。**
**环境与集群用法，看 [docs/setup.md](docs/setup.md)。**

## 分工状态

| 角色 | 认领人 | Issue |
|---|---|---|
| A 平台与基线 | SibeiLYU | [#1](https://github.com/mili5114/NLP_project/issues/1) |
| B 方法与冻结 | 待认领 | — |
| C 评测与展示 | 待认领 | — |

## 快速开始（集群）

```bash
git clone https://github.com/mili5114/NLP_project.git codeact-work
cd codeact-work
bash scripts/env/setup_env.sh                      # conda 环境 + 课程固定版本
export HF_ENDPOINT=https://hf-mirror.com
python scripts/env/fetch_model.py --out "$HOME/models"
sbatch scripts/env/smoke.sbatch                    # 冒烟：版本 / 显卡 / 模型 / 贪心生成
```

## 目录

| 路径 | 内容 | Owner |
|---|---|---|
| `configs/course/` | 课程原始附件（只读，程序直接读） | A 归档 |
| `configs/conditions/`、`configs/frozen/` | 四条件与冻结配置 | B |
| `src/runtime/`、`src/records/`、`src/feedback/baselines.py` | 后端、runner、观察器、记录、A/B 基线 | A |
| `src/feedback/selective.py`、`renderers.py` | C/D 反馈策略 | B |
| `src/evaluation/`、`scripts/score.py`、`results/` | 离线评分与汇总 | C |
| `scripts/export_references.py`、`references/` | 离线参考答案生成脚本 + 可提交的 hash 清单（答案原文不入公开仓库） | A |
| `runs/dev_baselines/`、`runs/dev_full_v3/`、`runs/eval/` | 各条件的交互日志（v3 = 当前协议下的完整 DEV 基线） | A / B / C |
| `docs/setup.md`、`docs/interfaces.md`、`docs/A_reference_export.md` | 环境说明、模块接口、参考答案导出说明 | A |

## 离线参考答案

评分用的参考答案由 `scripts/export_references.py` 从固定上游版本派生，覆盖 43 个任务（DEV 16 + EVAL 27）。
公开仓库只提交 hash 清单 `references/offline_reference_v1.manifest.json`；答案原文留在本地且被 `.gitignore` 排除。
复现命令、类型判定规则、隔离保证与校验方法见 [docs/A_reference_export.md](docs/A_reference_export.md)。

## 四条硬规矩

1. 每个文件 / 目录只有一个 Owner，别人不改，缺陷发回原 Owner。
2. EVAL 只能在冻结后跑；参考答案只进离线评分，不进 agent 上下文。
3. 失败任务全部保留，27 个任务全部进分母，不许重跑到成功。
4. 每次交接附一页代码地图 + 15 分钟讲解。
