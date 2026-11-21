#!/usr/bin/env python
"""环境自检 + 生成 configs/versions.json。

必须在**申请到 GPU 的作业里**跑（登录节点没有显卡）：
    sbatch scripts/env/smoke.sbatch

退出码：0 全部通过；1 有硬失败（版本不符 / 无 CUDA / 模型加载失败）。
"""
from __future__ import annotations

import argparse
import importlib.metadata as md
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone

PINNED = {
    "torch": "2.10.0",
    "transformers": "5.17.0",
    "tokenizers": "0.23.2",
    "accelerate": "1.15.0",
    "ipython": "8.37.0",
    "numpy": "2.2.6",
}
MODEL_REVISION = "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"
EOS_IDS = [248044, 248046]
UPSTREAM_COMMIT = "d607f56c9cfe9e8632ebaf65dcaf2b4b7fe1c6f8"

FAIL: list[str] = []


def check(ok: bool, msg: str) -> None:
    print(("  [ok]   " if ok else "  [FAIL] ") + msg)
    if not ok:
        FAIL.append(msg)


def pkg_versions() -> dict[str, str]:
    out = {}
    for name, want in PINNED.items():
        try:
            got = md.version(name)
        except md.PackageNotFoundError:
            got = "<missing>"
        out[name] = got
        check(got == want, f"{name} == {want} (实测 {got})")
    return out


def gpu_info() -> dict:
    info: dict = {"cuda_available": None, "devices": []}
    try:
        import torch
    except ImportError:
        check(False, "torch 未安装")
        return info
    info["cuda_available"] = torch.cuda.is_available()
    info["torch_cuda"] = torch.version.cuda
    check(bool(torch.cuda.is_available()), "torch.cuda.is_available()")
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            info["devices"].append(
                {
                    "index": i,
                    "name": props.name,
                    "total_memory_gb": round(props.total_memory / 1024**3, 1),
                    "capability": f"{props.major}.{props.minor}",
                }
            )
    try:
        smi = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=20, check=False,
        ).stdout.strip()
        info["nvidia_smi"] = smi
    except Exception as exc:  # noqa: BLE001
        info["nvidia_smi"] = f"<{type(exc).__name__}>"
    return info


def model_class():
    """优先用附件点名的类，不存在则回退并如实报告。"""
    import transformers
    if hasattr(transformers, "Qwen3_5ForConditionalGeneration"):
        return transformers.Qwen3_5ForConditionalGeneration, "Qwen3_5ForConditionalGeneration"
    return transformers.AutoModelForCausalLM, "AutoModelForCausalLM(fallback)"


def load_and_generate(model_dir: str, max_new_tokens: int) -> dict:
    import torch
    from transformers import AutoTokenizer

    cls, cls_name = model_class()
    check(
        cls_name == "Qwen3_5ForConditionalGeneration",
        f"类名 {cls_name}（期望 Qwen3_5ForConditionalGeneration）",
    )
    tok = AutoTokenizer.from_pretrained(model_dir)
    # 从本地目录加载，不带 revision（revision 在 fetch_model.py 下载阶段已固定并记录在
    # versions.json 里；本地路径再传 revision 可能触发一次多余的 hub 请求）。
    model = cls.from_pretrained(
        model_dir,
        torch_dtype=torch.bfloat16,
        device_map="cuda:0",
        attn_implementation="sdpa",
    )
    model.eval()

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Reply with exactly one word: ready"},
    ]
    kw = {"tokenize": False, "add_generation_prompt": True}
    try:
        text = tok.apply_chat_template(messages, enable_thinking=False, **kw)
    except TypeError:
        text = tok.apply_chat_template(messages, **kw)
    ids = tok(text, return_tensors="pt").to("cuda:0")

    with torch.no_grad():
        out = model.generate(
            **ids,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            eos_token_id=EOS_IDS,
            pad_token_id=tok.pad_token_id or tok.eos_token_id,
        )
    gen = out[0][ids["input_ids"].shape[1]:]
    reply = tok.decode(gen, skip_special_tokens=True)
    print(f"  [info] 生成结果: {reply!r}")
    return {
        "prompt_tokens": int(ids["input_ids"].shape[1]),
        "generated_tokens": int(gen.shape[0]),
        "reply": reply,
        "peak_gpu_mem_gb": round(torch.cuda.max_memory_allocated() / 1024**3, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", default=os.environ.get(
        "MODEL_DIR", os.path.expanduser("~/models/Qwen3.5-4B")))
    ap.add_argument("--write", default="configs/versions.json", help="写出版本记录；空字符串跳过")
    ap.add_argument("--max-new-tokens", type=int, default=32)
    ap.add_argument("--skip-model", action="store_true", help="只查依赖与显卡，不加载模型")
    args = ap.parse_args()

    print("== Python ==")
    print(f"  {sys.version.split()[0]}  ({platform.platform()})")
    check(sys.version_info[:2] == (3, 10), "Python == 3.10")

    print("== 固定依赖 ==")
    versions = pkg_versions()

    print("== GPU ==")
    gpu = gpu_info()

    gen = None
    if not args.skip_model:
        print("== 模型加载与贪心生成 ==")
        if not os.path.isdir(args.model_dir):
            check(False, f"模型目录不存在: {args.model_dir}")
        else:
            try:
                gen = load_and_generate(args.model_dir, args.max_new_tokens)
            except Exception as exc:  # noqa: BLE001
                check(False, f"模型加载/生成失败: {type(exc).__name__}: {exc}")

    record = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hostname": platform.node(),
        "python": sys.version.split()[0],
        "packages": versions,
        "upstream_code_commit": UPSTREAM_COMMIT,
        "model": {"repo_id": "Qwen/Qwen3.5-4B", "revision": MODEL_REVISION,
                  "dtype": "bfloat16", "backend": "transformers"},
        "decoding": {"do_sample": False, "enable_thinking": False,
                     "eos_token_ids": EOS_IDS, "stop_text": "End Action"},
        "gpu": gpu,
        "smoke": gen,
    }
    if args.write:
        path = os.path.abspath(args.write)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(record, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"\n[ok] 已写 {path}")

    print("\n== 结论 ==")
    if FAIL:
        for item in FAIL:
            print("  未通过：" + item)
        return 1
    print("  全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
