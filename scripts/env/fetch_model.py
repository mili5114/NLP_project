#!/usr/bin/env python
"""按课程固定 revision 拉取模型权重。必须在设置了 HF_ENDPOINT 的环境里运行。

    export HF_ENDPOINT=https://hf-mirror.com
    python scripts/env/fetch_model.py --out "$HOME/models"
"""
import argparse
import json
import os
import sys

REPO_ID = "Qwen/Qwen3.5-4B"
REVISION = "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="权重落盘目录（不要放仓库内）")
    ap.add_argument("--repo-id", default=REPO_ID)
    ap.add_argument("--revision", default=REVISION)
    args = ap.parse_args()

    if not os.environ.get("HF_ENDPOINT"):
        print("[warn] HF_ENDPOINT 未设置；集群直连 huggingface.co 会超时", file=sys.stderr)
        print("       建议：export HF_ENDPOINT=https://hf-mirror.com", file=sys.stderr)

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("[error] 缺 huggingface_hub，先跑 scripts/env/setup_env.sh", file=sys.stderr)
        return 2

    os.makedirs(args.out, exist_ok=True)
    path = snapshot_download(
        repo_id=args.repo_id,
        revision=args.revision,
        local_dir=os.path.join(args.out, args.repo_id.split("/")[-1]),
        ignore_patterns=["*.pth", "*.gguf", "original/*"],
    )
    print("[ok] 权重目录:", path)

    # 记录实际落盘的 commit，用于 configs/versions.json
    meta = os.path.join(path, ".cache", "huggingface", "download", "*.metadata")
    info = {"repo_id": args.repo_id, "requested_revision": args.revision, "local_dir": path}
    config = os.path.join(path, "config.json")
    if os.path.exists(config):
        with open(config, encoding="utf-8") as fh:
            cfg = json.load(fh)
        info.update({k: cfg.get(k) for k in ("architectures", "torch_dtype", "num_hidden_layers")})
    print(json.dumps(info, ensure_ascii=False, indent=2))
    print("\n把上面这段写进 configs/versions.json 的 model 段（脚本不自动改仓库文件）。")
    _ = meta
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
