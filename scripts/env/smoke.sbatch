#!/usr/bin/env bash
#SBATCH --job-name=a-sibei-smoke
#SBATCH --partition=i64m1tga800u
#SBATCH --gres=gpu:a800:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=00:30:00
#SBATCH --output=logs/smoke-%j.out
#SBATCH --error=logs/smoke-%j.err

# 冒烟测试：验证 conda 环境、依赖版本、模型加载、贪心生成、EOS 行为。
# 提交：sbatch scripts/env/smoke.sbatch
set -euo pipefail

cd "${SLURM_SUBMIT_DIR:-$HOME/codeact-work}"
mkdir -p logs

module load anaconda3
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate codeact

export HF_ENDPOINT=https://hf-mirror.com
export TOKENIZERS_PARALLELISM=false
export HF_HUB_OFFLINE=1
export MODEL_DIR="${MODEL_DIR:-$HOME/models/Qwen3.5-4B}"

echo "job=$SLURM_JOB_ID node=$(hostname) date=$(date -Is)"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader

python scripts/env/check_env.py --model-dir "$MODEL_DIR" --write configs/versions.json
echo "exit=$?"
