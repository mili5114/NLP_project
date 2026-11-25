#!/usr/bin/env bash
#SBATCH --job-name=bench
#SBATCH --partition=i64m1tga40u
#SBATCH --gres=gpu:a40:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=00:20:00
#SBATCH --output=logs/bench-%j.out
#SBATCH --error=logs/bench-%j.err

# 速度基准：测架构 / 内核（fla、causal_conv1d）/ 模板 thinking / tok/s。
# 用法：sbatch scripts/env/bench.sbatch
set -euo pipefail

cd "${SLURM_SUBMIT_DIR:-$HOME/codeact-work}"
mkdir -p logs

module load anaconda3
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate codeact

echo "job=$SLURM_JOB_ID node=$(hostname) date=$(date -Is)"
nvidia-smi --query-gpu=name --format=csv,noheader

python scripts/env/bench_speed.py
