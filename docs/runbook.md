# 运行说明（A 维护）

> 目标：别人按本文能在集群上从零跑到"一个 DEV 任务"和"完整 DEV A/B 32 个槽位"。
> 环境事实与版本见 `docs/env_and_config.md`；字段含义见 `docs/log_fields.md`。

## 1. 一次性环境准备（约 40 分钟）

```bash
ssh aiaa4051_038@hpc2login.hpc.hkust-gz.edu.cn      # 首次登录必须先到门户改初始密码
git clone https://github.com/mili5114/NLP_project.git ~/codeact-work
cd ~/codeact-work
bash scripts/env/setup_env.sh                        # conda create -n codeact python=3.10 + 固定依赖 + 冻结 lock
bash scripts/env/fetch_model.sh ~/models/Qwen3.5-4B  # 走 ModelScope（HF 直连不通），逐文件 sha256 核对
sbatch scripts/env/smoke.sbatch                      # debug 分区拿一张 A40，约 1 分钟
cat logs/smoke-*.out                                 # 期望：全部 PASS + peak_gpu_mem_gb
```

`scripts/env/check_env.py` 会断言 Python 3.10、六个版本号、CUDA、类名、`do_sample=False`、`enable_thinking=False`、EOS。冒烟实测输出在 `runs/smoke/14051595.out`。

## 2. 单任务验证（先确认服务器代码是目标 commit）

```bash
cd ~/codeact-work
git fetch origin && git checkout <目标commit>        # 例：7af057d
git status --short && git rev-parse HEAD              # 必须 clean，且 HEAD == 目标 commit

COND=A \
RUNS_ROOT=runs/dev_fix_check_v3 \
TASKS="travel_itinerary_planning/cheapest_new_york_trip" \
sbatch --partition=i64m1tga40u --gres=gpu:a40:1 --time=00:30:00 scripts/env/gpu_job.sbatch
```

- **变量写在提交命令的环境里，不要写进 `--export=`**：`--export=ALL,COND=A,TASKS=a,b` 里的逗号是环境变量分隔符，`TASKS` 会被截成 `a`（v1 只跑了 travel 一个任务就是这个原因）。多任务用空格分隔：`TASKS="task/one task/two"`。
- `RUNS_ROOT` 每批一个新目录，不覆盖旧记录。
- 读结果：`episode.json`（`status`/`termination_reason`/`final_answer`）、`turns.jsonl`（逐轮）、`manifest.json`（`team_commit` 是否等于目标 commit）。

## 3. 完整 DEV A/B（16 任务 × 2 条件 = 32 个唯一槽位）

```bash
cd ~/codeact-work
COND=A RUNS_ROOT=runs/dev_full_v3 SPLIT=DEV sbatch --partition=i64m1tga800u --gres=gpu:a800:1 --time=02:00:00 scripts/env/gpu_job.sbatch   # 作业名 devfull3-A
COND=B RUNS_ROOT=runs/dev_full_v3 SPLIT=DEV sbatch --partition=i64m1tga800u --gres=gpu:a800:1 --time=02:00:00 scripts/env/gpu_job.sbatch   # 作业名 devfull3-B
squeue -u $USER
```

- 不给 `TASKS` 就按 `configs/course/split_manifest.json` 的 DEV 全量跑（16 条），顺序即清单顺序。
- 失败、无答案、超时、预算耗尽**一律保留，不重跑到成功**；单题异常会写一条 `status=error` 的 episode，不会中断整批。
- 2 小时上限的依据：16 题 × 180s 截止 + 加载/预热，实测单批 11–25 分钟；上限只防卡死。
- 取回：

```bash
# 在集群打包，本地再解（避免半截文件）
cd ~/codeact-work && tar czf ~/dev_full_v3.tar.gz runs/dev_full_v3
# 本地
scp aiaa4051_038@10.120.18.63:~/dev_full_v3.tar.gz . && tar xzf dev_full_v3.tar.gz -C NLP_project/
```

## 4. 本地复核与评分（不占 GPU）

```bash
cd NLP_project
python -m unittest discover -s tests                                   # 期望：97 passed
python scripts/config_fingerprint.py runs/dev_full_v3/DEV              # 32 条 manifest 必须只有 1 个 fingerprint
python scripts/run_stats.py --runs runs/dev_full_v3/DEV                 # 结果概览（只读 episode.json，不做正确性判定）
python scripts/score.py --episodes runs/dev_full_v3/DEV \
    --references references/offline_reference_v1.json \
    --out runs/dev_full_v3/scored.jsonl                                 # C 的离线评分 CLI，逐任务 success
```

- `references/offline_reference_v1.json` 是**离线答案**（不进公开仓库，`.gitignore` 已挡），需要用 `python scripts/export_references.py` 在本机或集群重新生成；`references/offline_reference_v1.manifest.json` 是可提交的 hash 清单，用来核对两人导出的是同一份答案。
- 评分只做 `numeric`（Decimal 比较）/`string`（strip 后 exact match），不做"看起来对不对"的猜测。

## 5. 常见坑

1. **投作业前先确认 HEAD**：曾经在服务器还是旧代码时投了两个作业，只能 scancel 重投。`manifest.team_commit` 是唯一凭据。
2. **别把数据提交 pull 到服务器**：`git pull` 会把 HEAD 移到数据提交，之后新作业的 `team_commit` 就变成数据提交。
3. **`--export` 的逗号会截断 `TASKS`**：见 §2。
4. **每次新 clone 的子模块是空目录**：`gpu_job.sbatch` 会自动 `git submodule update --init --recursive`，手动跑 runner 时要先补这一步，否则 import 上游任务时报错。
5. **Triton/FLA 内核缓存要固定**：`TRITON_CACHE_DIR` 由 sbatch 设到 `~/.triton_cache_codeact`，跨作业复用；不设的话每次新作业多花约 40s 重新 JIT。
6. **计算节点可能不能出网**：作业里 `HF_HUB_OFFLINE=1` 只读本地权重；web_browsing 任务用的是仓库内 `web_pages.jsonl`，不需要外网。
7. **共享账号**：作业名带用途（`devfull3-A` 等），`runs/` 每批一个目录，避免互相覆盖。
