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

# TODO(A)：runner 入口落地后启用。当前 src/runtime 只有骨架，先不要跑。
# python -m src.runtime.runner \
#     --config configs/course/runtime_settings.json \
#     --split configs/course/split_manifest.json \
#     --condition "$COND" \
#     --model-dir "$MODEL_DIR" \
#     --out "runs/dev_baselines/sibei/${COND}" \
#     --tasks "${TASKS:-}"

echo "runner 尚未实现，本作业仅验证节点与环境。"
python scripts/env/check_env.py --model-dir "$MODEL_DIR" --skip-model
