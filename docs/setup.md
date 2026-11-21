# 环境与运行说明（A 维护）

> 最后更新：2026-11-21。状态：集群已探明、脚本已就绪，尚未在 GPU 节点上跑过任何任务。
> 本文件记录**实测到的事实**与**待确认项**，不含凭据；账号密码只在教师邮件与本地密码管理器里。

## 1. 集群事实（实测）

| 项目 | 实测值 | 备注 |
|---|---|---|
| 登录入口 | `10.120.18.63`（`mgmt-3`） | 本机直连 22 端口可达；`10.120.18.240`（`login.hpc…`）从校外网络超时 |
| Slurm 集群名 | `hkuhpc-ai` | 控制节点 `10.120.18.242` |
| GPU 节点 | `gpu1-1` … | `Gres=gpu:a800:8`，**每节点 8 张 A800**，64 核 / 503 GB 内存 |
| GPU 分区 | `i64m1tga800u`（A800）、`i64m1tga40u`（A40） | 单作业最长 7 天；另有 `long_gpu`（14 天）、`debug`（30 分钟）、`emergency_gpu` |
| 调度配额 | QOS：`gpu16` / `gpu24` / `gpu32` 等 | 并发 GPU 数上限，具体按课程分配确认（见 §6） |
| 软件模块 | `module load anaconda3` → conda 24.7.1 / Python 3.11.9 | 系统 `/usr/bin/python3` 只有 3.8，**不能用** |
| 家目录 | `/hpc2hdd/home/aiaa4051_038` | 所在文件系统 3.9 P / 余量 256 T；当前无个人 quota 显示 |
| 账号性质 | 课程共享账号，队列里能看到全部同学作业 | 作业名与目录必须带姓名，见 §5 |

## 2. 首次准备（一次性，约 40 分钟）

### 2.1 登录

```bash
ssh aiaa4051_038@10.120.18.63
```

建议配置免密（不要提交私钥到仓库）：

```bash
ssh-keygen -t ed25519 -C "aiaa4051_038@sibei"     # 本地执行
ssh-copy-id aiaa4051_038@10.120.18.63
```

### 2.2 建环境

```bash
cd ~
git clone https://github.com/mili5114/NLP_project.git codeact-work
cd codeact-work
bash scripts/env/setup_env.sh
```

脚本做的事：`module load anaconda3` → `conda create -n codeact python=3.10` → 按
`requirements.txt` 装课程指定版本 → 冻结完整依赖到 `configs/locks/`。

### 2.3 下载模型（9.3 GB）

```bash
bash scripts/env/fetch_model.sh ~/models/Qwen3.5-4B
```

**不要用 `huggingface_hub` 直连**。实测：集群直连 `huggingface.co` 超时，`hf-mirror.com`
只有 0.26 MB/s（9.3 GB 要 10 小时），**ModelScope 8–13 MB/s（约 15 分钟）**。
`fetch_model.sh` 走 ModelScope，逐文件 `curl -C -` 断点续传，最后用 sha256 与
HuggingFace 官方 `lfs.sha256` 比对；两个分片的哈希已实测一致，记录在
`configs/model_provenance.json`。

固定 `Qwen/Qwen3.5-4B`，revision `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`。
`scripts/env/fetch_model.py` 保留为 HF 方案备用（镜像快的时候再用）。

### 2.4 冒烟测试（拿一张卡，约 5 分钟）

```bash
sbatch scripts/env/smoke.sbatch
squeue -u $USER
cat logs/smoke-*.out        # 期望：venv 版本表 + 1 次贪心生成的 token 数
```

`scripts/env/check_env.py` 会断言：Python 3.10、六个版本号、CUDA 可用、类名
`Qwen3_5ForConditionalGeneration` 是否真实存在（不存在则回退 `AutoModelForCausalLM`
并明确报告）、`do_sample=False`、`enable_thinking=False`、EOS 248044/248046。
输出同时写入 `configs/versions.json`（由脚本生成，不手填）。

## 3. 运行正式实验

```bash
sbatch scripts/env/gpu_job.sbatch      # 单卡、8 核、64G、最长 6 小时
```

作业内先 `export HF_ENDPOINT`、`conda activate codeact`，再调 `python -m src.runtime.runner`。
runner 入口在 `src/runtime/`，接口见 `docs/interfaces.md`。

## 4. 记录必须落地的字段

每个 episode 三件套（`manifest.json` / `turns.jsonl` / `episode.json`），字段定义见
`docs/interfaces.md` §3。GPU 用量另写 `runs/<split>/ledger.md`：作业号、卡数、起止时间、
对应 run_id、失败原因。课程上限 < 100 GPU-hours，按 pilot 15% / DEV 30% / EVAL 30% /
修复 10% / 余量 15% 内部规划。

## 5. 已知坑

1. **REPL 限时依赖 `signal.SIGALRM`**：上游 `tasks/repl.py` 只能在 Linux 主线程跑，本机 Windows 不可用。所有实验都在集群上跑。
2. **`huggingface.co` 不可直连**：每个作业都必须在脚本里 `export HF_ENDPOINT=https://hf-mirror.com`，否则模型加载会卡在重试。权重只在**登录节点**下好；计算节点不一定能出网，作业里应设 `HF_HUB_OFFLINE=1` 只读本地缓存。
   - 好消息：`web_browsing` 四类任务的网页数据是仓库内的 `tasks/impl/web_browsing/web_pages.jsonl`，工具不访问外网，作业可以在无网的计算节点上跑。
3. **答案泄漏点**：`Task.__init__` 会 `print` 出 `expected_output`，`main.py` 答错还会回一句 "Your answer is incorrect"。两者都必须在 runner 里切断，标准答案只进私有日志与离线评分。
4. **共享账号**：`squeue` 能看到全班作业，别人也能看到你的。作业名统一 `a-sibei-<用途>`，`runs/` 下每个 run 带 `sibei/` 前缀，避免互相覆盖。
5. **`sinfo`/`scontrol` 在 mgmt-3 上要带 `-M hkuhpc-ai`**，否则报 `unable to status file /etc/slurm-llnl/slurm.conf`。
6. **家目录剩余量**：文件系统整体已用 94%，权重和日志别堆在 `~`，优先 `/hpc2hdd/home/$USER/models`。

## 6. 待确认

- [ ] 教师指定的正式登录地址是 `10.120.18.63` 还是别的（`login.hpc…` 校外不可达）。
- [ ] 单作业申请 GPU 是否需要显式 `--qos=gpu16`，还是账号默认 QOS 就够。
- [ ] 课程 100 GPU-hours 如何计量（作业时长 × 卡数，还是 Slurm TRES 累计），谁负责汇总。
- [ ] 是否能申请到 `long_gpu` 分区（14 天），用于 32 条 DEV 的一次性长跑。
