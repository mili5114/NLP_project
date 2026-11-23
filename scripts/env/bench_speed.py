"""诊断生成速度：架构 / 模板 / 设备分布 / tok/s / attn 实现。"""
import json
import time

import torch
import transformers
from transformers import AutoTokenizer

MODEL_DIR = "/hpc2hdd/home/aiaa4051_038/models/Qwen3.5-4B"
cfg = json.load(open(f"{MODEL_DIR}/config.json"))
print("model_type:", cfg.get("model_type"))
print("architectures:", cfg.get("architectures"))
for mod in ("causal_conv1d", "fla", "flash_attn"):
    try:
        m = __import__(mod)
        print(f"kernel {mod}: OK", getattr(m, "__version__", "?"))
    except Exception:
        print(f"kernel {mod}: MISSING")

tok = AutoTokenizer.from_pretrained(MODEL_DIR)
msgs = [{"role": "system", "content": "hi"}, {"role": "user", "content": "hello"}]
r_def = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
try:
    r_nt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
except TypeError:
    r_nt = None
print("template default tail:", repr(r_def[-100:]))
print("template nothink tail:", repr(r_nt[-100:]) if r_nt else "enable_thinking kwarg NOT ACCEPTED")
print("same:", r_def == r_nt if r_nt else "-")

cls = getattr(transformers, "Qwen3_5ForConditionalGeneration", None) or transformers.AutoModelForCausalLM
model = cls.from_pretrained(
    MODEL_DIR, torch_dtype=torch.bfloat16, device_map="cuda:0", attn_implementation="sdpa"
)
model.eval()
print("param devices:", {str(p.device) for p in model.parameters()})
print("torch threads:", torch.get_num_threads(), "cuda threads:", torch.get_num_interop_threads())

PAD = tok.pad_token_id or tok.eos_token_id


def bench(ids, gen, label):
    torch.cuda.synchronize(); t0 = time.perf_counter()
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=gen, do_sample=False, pad_token_id=PAD)
    torch.cuda.synchronize(); dt = time.perf_counter() - t0
    if hasattr(out, "sequences"):
        seq = out.sequences
    elif isinstance(out, torch.Tensor):
        seq = out
    elif isinstance(out, (list, tuple)):
        seq = out[0] if out else None
    else:
        seq = out
    if seq is None or not hasattr(seq, "shape"):
        print(f"{label}: {dt:.2f}s, but output type={type(out)} — no token count", flush=True)
        return
    n = int(seq.shape[1] - ids["input_ids"].shape[1])
    print(f"{label}: {n} tok in {dt:.2f}s = {n / dt:.2f} tok/s", flush=True)


ids_short = tok("User: hello. Assistant:", return_tensors="pt").to("cuda:0")
bench(ids_short, 32, "short-prompt")
long_text = "The quick brown fox jumps over the lazy dog. " * 80
ids_long = tok(long_text, return_tensors="pt").to("cuda:0")
print("long prompt tokens:", int(ids_long["input_ids"].shape[1]))
bench(ids_long, 64, "long-prompt")

# 逐 token 计时（不依赖 generate 的循环），看 forward 本身速度
try:
    ids = ids_short
    with torch.no_grad():
        out = model(**ids, use_cache=True)
    past = out.past_key_values
    nxt = out.logits[:, -1:].argmax(-1)
    torch.cuda.synchronize(); t0 = time.perf_counter()
    with torch.no_grad():
        for _ in range(20):
            out = model(nxt, past_key_values=past, use_cache=True)
            nxt = out.logits[:, -1:].argmax(-1)
    torch.cuda.synchronize(); dt = time.perf_counter() - t0
    print(f"manual decode: 20 tok in {dt:.2f}s = {20 / dt:.2f} tok/s", flush=True)
except Exception as exc:
    print(f"manual decode failed: {type(exc).__name__}: {exc}")
print("peak mem GB:", round(torch.cuda.max_memory_allocated() / 1024**3, 2))
