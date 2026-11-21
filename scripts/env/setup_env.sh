#!/usr/bin/env bash
# 一次性环境准备。在集群登录节点执行：bash scripts/env/setup_env.sh
# 幂等：已存在的 conda 环境会复用，只补装缺的包。
set -euo pipefail

ENV_NAME="${ENV_NAME:-codeact}"
PY_VER="3.10"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "==> [1/4] 加载 conda"
if ! command -v conda >/dev/null 2>&1; then
    module load anaconda3
    # shellcheck disable=SC1091
    source "$(conda info --base)/etc/profile.d/conda.sh"
fi
conda --version

echo "==> [2/4] 创建/复用环境 ${ENV_NAME} (python ${PY_VER})"
if conda env list | awk '{print $1}' | grep -qx "${ENV_NAME}"; then
    echo "    环境已存在，跳过创建"
else
    conda create -y -n "${ENV_NAME}" "python=${PY_VER}"
fi
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "${ENV_NAME}"
python -V

echo "==> [3/4] 安装课程固定版本（requirements.txt）"
python -m pip install --upgrade pip
python -m pip install -r "${REPO_ROOT}/requirements.txt"

echo "==> [4/4] 冻结完整依赖到 configs/locks/"
mkdir -p "${REPO_ROOT}/configs/locks"
LOCK="${REPO_ROOT}/configs/locks/env-$(date +%Y%m%d-%H%M%S).txt"
{
    echo "# $(hostname) / $(date -Is)"
    echo "# conda env: ${ENV_NAME} / $(python -V 2>&1)"
    python -m pip freeze
} > "${LOCK}"
echo "    -> ${LOCK}"

cat <<'TIP'

下一步：
  export HF_ENDPOINT=https://hf-mirror.com
  python scripts/env/fetch_model.py --out "$HOME/models"
  sbatch scripts/env/smoke.sbatch
TIP
