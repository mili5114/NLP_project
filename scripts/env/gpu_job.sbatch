#!/usr/bin/env bash
#SBATCH --job-name=a-sibei-run
#SBATCH --partition=i64m1tga800u
#SBATCH --gres=gpu:a800:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=06:00:00
#SBATCH --output=logs/run-%j.out
#SBATCH --error=logs/run-%j.err

# 通用运行模板：一次作业跑一个 condition 的若干 DEV 任务。
# 用法：
#   COND=A TASKS=msg_decoder,trade_calc sbatch scripts/env/gpu_job.sbatch
#   sbatch --export=ALL,COND=B scripts/env/gpu_job.sbatch
set -euo pipefail

cd "${SLURM_SUBMIT_DIR:-$HOME/codeact-work}"
mkdir -p logs runs/dev_baselines

# 新 clone 的仓库子模块是空目录，不初始化会在 import m3tooleval 时崩掉。
if [ ! -f third_party/code-act/scripts/eval/m3tooleval/tasks/base.py ]; then
    echo "[setup] upstream submodule empty, initializing..."
    git submodule update --init --recursive
fi

module load anaconda3
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate codeact

export HF_ENDPOINT=https://hf-mirror.com
export TOKENIZERS_PARALLELISM=false
export HF_HUB_OFFLINE=1
export MODEL_DIR="${MODEL_DIR:-$HOME/models/Qwen3.5-4B}"
export COND="${COND:-A}"

echo "job=$SLURM_JOB_ID node=$(hostname) cond=$COND date=$(date -Is)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

# 任务列表：TASKS 用空格或逗号分隔的 task_id；不给就按 SPLIT 跑全部
TASK_ARGS=()
if [ -n "${TASKS:-}" ]; then
    for t in ${TASKS//,/ }; do TASK_ARGS+=(--task "$t"); done
fi

python -m src.runtime.runner \
    --split "${SPLIT:-DEV}" \
    --condition "$COND" \
    --model-dir "$MODEL_DIR" \
    --runs-root "${RUNS_ROOT:-runs/dev_baselines}" \
    --limit "${LIMIT:-0}" \
    "${TASK_ARGS[@]}"
