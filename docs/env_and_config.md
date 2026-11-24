# 代码、环境与配置口径（A 维护）

> 最后更新：2026-11-24 22:30。本文只写**实测到的事实**。凭据不在此文件。

## 1. 代码版本

| 用途 | commit | 说明 |
|---|---|---|
| 课程指定上游 | `d607f56c9cfe9e8632ebaf65dcaf2b4b7fe1c6f8` | 记录在每个 `manifest.json` 的 `upstream_commit` |
| 基线运行代码（v2 验证 + 完整 DEV 批次） | `7af057d46c091181a363fac7ff055efc5fc297d5` | 记录在每个 `manifest.json` 的 `team_commit`；**这是"这批数据由哪份代码产生"的唯一依据** |
| 当前 HEAD | `fc67310` | 只改记录字段（时间戳）与测试，不改预算、提示词、解码参数；见 §4 |

提交前的未提交状态：服务器工作区 `git status --porcelain` 为空（无 modified / untracked），即提交出去的代码与实际跑的代码一致。判定方法：`cd ~/codeact-work && git status --short && git rev-parse HEAD`。

**投作业前必须确认服务器 HEAD 就是目标 commit，且不要为了拿数据把数据提交 pull 到服务器**——否则 `team_commit` 会漂移成数据提交，批次就不再是"同一份代码"。

## 2. 模型、后端与运行环境

| 项 | 值 | 来源 |
|---|---|---|
| 模型 | `Qwen/Qwen3.5-4B`，revision `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a` | `configs/versions.json`、每个 manifest 的 `model.revision` |
| tokenizer | 同一 repo 同一 revision（`tokenizer.json` sha256 `5f9e4d49…1cb42`，12.8 MB） | `configs/model_provenance.json` |
| 后端 | 本地 HF `transformers`（class `Qwen3_5ForConditionalGeneration`，`attn_implementation=sdpa`，`device=cuda:0`） | `src/runtime/backend.py`、`configs/versions.json` |
| 解码 | BF16、greedy（`do_sample=false`）、`enable_thinking=false`、EOS `248044/248046`、停止串 `End Action` | `configs/course/runtime_settings.json` |
| Python | 3.10.22（conda env `codeact`） | `configs/versions.json` |
| 关键包 | torch 2.10.0 / transformers 5.17.0 / tokenizers 0.23.2 / accelerate 1.15.0 / ipython 8.37.0 / numpy 2.2.6 | `requirements.txt` 固定，`configs/locks/env-20261121-160506.txt` 冻结全部 90 行 |
| GPU（v1/v2 验证） | NVIDIA A40 47.4 GB，分区 `i64m1tga40u`，1 卡 / 8 核 / 64 GB | `sacct`、`docs/gpu_ledger.md` |
| GPU（完整 DEV 批次） | NVIDIA A800，分区 `i64m1tga800u`，1 卡 / 8 核 / 64 GB | 作业脚本 `scripts/env/gpu_job.sbatch` + `sacct` 的 `ReqTRES` |

权重完整性：`configs/model_provenance.json` 记录 ModelScope 下载来源与逐文件 sha256。当前**只有** `model.safetensors-00001-of-00002` 与 HuggingFace 官方 `lfs.sha256` 核对一致；第二分片与 `tokenizer.json` 已记本地 sha256 与字节数，但未取得官方 sha256 → 状态记"部分验证"（不假装全验证）。

## 3. 两个 hash 的区别（容易被混用）

| 名字 | 是什么 | 在哪 | 回答什么问题 |
|---|---|---|---|
| 课程设置 hash（`config_sha256` / `course_hashes["runtime_settings.json"]`） | `configs/course/runtime_settings.json` **文件内容**的 sha256 = `faa79929…dfdd1` | 每个 `episode.json.config_sha256`、每个 manifest 的 `course_hashes` | 课程设置有没有被改动？ |
| 完整运行配置 hash（`config_fingerprint`） | 把实际生效配置规范化后取 sha256：课程 hash + 上游/团队 commit + 模型 revision + 解码设置 + 全部 limits + 停止串 + `backend` | `python scripts/config_fingerprint.py <batch>` 现算 | 两次运行是不是同一份配置在跑？ |

同一课程 hash 可以对应不同的 `config_fingerprint`（代码 commit 不同、模型 revision 不同）。**交接口径用 `config_fingerprint` 判断"同批同协议"，用课程 hash 证明"没动课程文件"**。

已算出的值：

| 批次 | `config_fingerprint` | `team_commit` |
|---|---|---|
| `runs/dev_fix_check_v2`（v2 验证样例，A/B） | `e4fe086ff67af7fa673189a78009ae6caca18c54db165164d7418757584d0bb9` | `7af057d` |
| `runs/dev_baselines`（首轮 16×2 + pilot，仅诊断） | `27bc27436d248f4e19c8e8d4a040ec3cb1744b586504c31f12092a9c52484495` | `8c1f481` |
| `runs/dev_full_v3`（完整 DEV，32 槽位） | 数据落盘后用同一命令算，写进 `runs/index.md` | `7af057d` |

`config_fingerprint` 里**不含 GPU 型号**：GPU 不改课程协议，只影响速度与数值细节，所以单独记在 `docs/gpu_ledger.md`（作业号、卡数、起止时间、GPU 时长口径）。

## 4. `fc67310` 改了什么（为什么基线数据不是这个 commit）

只改记录与测试：

- `turns.jsonl` 每轮增加 `generation_seconds` / `finish_reason` / `cut_by_deadline` / `generation_stopped_at` / `generation_stopped_task_seconds`；
- `episode.json` 增加 `task_started_at` / `task_deadline_at` / `generation_stopped_at` / `episode_written_at` / `post_generation_seconds` / `deadline_overrun_seconds` / `deadline_exceeded`；
- 新增 2 个 CPU 回归（到点截断语义 + 时间字段），全量测试 97 条通过。

不涉及：`limits` 任何数值、system prompt / contract / 最终轮请求、解码参数、工具观察器、反馈层。因此 `7af057d` 产出的数据在协议上与 `fc67310` 等价，差别只是旧数据要用派生口径读时间（见 `docs/log_fields.md` §8）。

旧数据（`7af057d` 及以前）与 `8c1f481`（首轮基线）的区别见 `docs/failure_taxonomy.md`：首轮那批 **提示词签名是错的**，只能作诊断材料，不能当基线。**首轮 DEV/EVAL 记录不进入新基线。**
