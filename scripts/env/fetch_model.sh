#!/usr/bin/env bash
# 拉取 Qwen3.5-4B 权重并校验 sha256。
#
# 为什么不用 huggingface_hub：集群直连 huggingface.co 不通；hf-mirror.com 实测只有
# ~0.26 MB/s（9.3 GB 要 10 小时），ModelScope 实测 8–13 MB/s（约 15 分钟）。
# 两个分片的 sha256 已与 HuggingFace 官方 lfs oid 逐字节比对一致，来源可追溯。
#
# 用法：bash scripts/env/fetch_model.sh [目标目录]
set -euo pipefail

DEST="${1:-$HOME/models/Qwen3.5-4B}"
BASE="https://modelscope.cn/models/Qwen/Qwen3.5-4B/resolve/master"
mkdir -p "$DEST"
cd "$DEST"

SMALL="config.json chat_template.jinja merges.txt model.safetensors.index.json \
preprocessor_config.json tokenizer.json tokenizer_config.json \
video_preprocessor_config.json vocab.json"

fetch() {
    local f="$1"
    echo "[$(date +%T)] $f"
    for _ in 1 2 3 4 5; do
        curl -fL -C - --retry 10 --retry-delay 3 -m 7200 -o "$f" "$BASE/$f" && return 0
        echo "[$(date +%T)] 重试 $f"
        sleep 3
    done
    echo "[fail] $f" >&2
    return 1
}

for f in $SMALL; do fetch "$f"; done
fetch "model.safetensors-00001-of-00002.safetensors"
fetch "model.safetensors-00002-of-00002.safetensors"

echo "== 校验 =="
check() {
    local f="$1" want="$2"
    local got
    got=$(sha256sum "$f" | cut -d' ' -f1)
    if [ "$got" = "$want" ]; then
        echo "  [ok]   $f"
    else
        echo "  [FAIL] $f" >&2
        echo "         期望 $want" >&2
        echo "         实际 $got" >&2
        return 1
    fi
}
check model.safetensors-00001-of-00002.safetensors 26a93f066e1916adb13453dae5a0c707c0fbc71299ed98779571a907b8e74c61
check model.safetensors-00002-of-00002.safetensors cb544bd9bfae93dc59b0f22b292f5933573854a7f9b97835c67060d7d910e188
check tokenizer.json 5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42

echo "完成：$DEST"
