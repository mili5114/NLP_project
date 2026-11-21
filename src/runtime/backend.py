"""模型后端。

上游 `main.py` 用 `openai.ChatCompletion`（0.x API），本地没有这个服务，所以换成两种实现：
- `TransformersBackend`：课程指定的本地 HF 推理，BF16 + greedy + non-thinking。
- `FakeBackend`：脚本化的假模型，用于在不占 GPU 的情况下验证预算、计数与终止语义。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Generation:
    text: str
    prompt_tokens: int
    completion_tokens: int
    elapsed_seconds: float
    hit_stop: bool = False
    finish_reason: str = "length"


class Backend(Protocol):
    name: str

    def generate(self, messages: list[dict[str, str]], *, max_new_tokens: int) -> Generation: ...


def cut_at_stop(text: str, stop_text: str) -> tuple[str, bool]:
    """把生成结果截到 stop 串（含）。模型多写了后续内容也不让它们进 messages。"""
    if not stop_text:
        return text, False
    idx = text.find(stop_text)
    if idx == -1:
        return text, False
    return text[: idx + len(stop_text)], True


@dataclass
class FakeBackend:
    """按顺序吐出预设回复。用完后重复最后一条（便于测试 12 轮耗尽）。"""

    replies: list[str]
    prompt_tokens_per_call: int = 100
    stop_text: str = "End Action"
    name: str = "fake"
    calls: int = 0
    seen_messages: list[list[dict[str, str]]] = field(default_factory=list)

    def generate(self, messages: list[dict[str, str]], *, max_new_tokens: int) -> Generation:
        self.seen_messages.append([dict(m) for m in messages])
        if not self.replies:
            raise RuntimeError("FakeBackend 没有配置回复")
        idx = min(self.calls, len(self.replies) - 1)
        raw = self.replies[idx]
        self.calls += 1
        text, hit = cut_at_stop(raw, self.stop_text)
        # 用字符数近似 token 数即可；真实 token 统计只来自 TransformersBackend
        completion = min(len(text), max_new_tokens)
        return Generation(
            text=text,
            prompt_tokens=self.count_tokens(messages),
            completion_tokens=completion,
            elapsed_seconds=0.0,
            hit_stop=hit,
            finish_reason="stop" if hit else "length",
        )

    def count_tokens(self, messages: list[dict[str, str]]) -> int:
        return max(1, sum(len(m.get("content", "")) for m in messages) // 4)


class TransformersBackend:
    """本地 HF 推理。构造时加载权重（约 8 GB，A40 上 20 秒内）。"""

    name = "transformers"

    def __init__(
        self,
        model_dir: str,
        *,
        class_name: str = "Qwen3_5ForConditionalGeneration",
        dtype: str = "bfloat16",
        device: str = "cuda:0",
        attn_implementation: str = "sdpa",
        eos_token_ids: list[int] | None = None,
        stop_text: str = "End Action",
    ) -> None:
        import torch
        import transformers
        from transformers import AutoTokenizer

        self.torch = torch
        self.stop_text = stop_text
        self.eos_token_ids = eos_token_ids or [248044, 248046]
        self.device = device

        cls = getattr(transformers, class_name, None)
        if cls is None:
            cls = transformers.AutoModelForCausalLM

        torch_dtype = getattr(torch, dtype)
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self.model = cls.from_pretrained(
            model_dir,
            torch_dtype=torch_dtype,
            device_map=device,
            attn_implementation=attn_implementation,
        )
        self.model.eval()

    def _render(self, messages: list[dict[str, str]]) -> str:
        kw = {"tokenize": False, "add_generation_prompt": True}
        for extra in ({"enable_thinking": False}, {}):
            try:
                return self.tokenizer.apply_chat_template(messages, **extra, **kw)
            except TypeError:
                continue
            except Exception:  # noqa: BLE001 - 少数模板不接受 system-only，补一句 user 再试
                break
        return self.tokenizer.apply_chat_template(
            [*messages, {"role": "user", "content": "Begin."}], **kw
        )

    def count_tokens(self, messages: list[dict[str, str]]) -> int:
        return int(len(self.tokenizer(self._render(messages))["input_ids"]))

    def generate(self, messages: list[dict[str, str]], *, max_new_tokens: int) -> Generation:
        started = time.perf_counter()
        text = self._render(messages)
        ids = self.tokenizer(text, return_tensors="pt").to(self.device)
        prompt_tokens = int(ids["input_ids"].shape[1])

        with self.torch.no_grad():
            out = self.model.generate(
                **ids,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                eos_token_id=self.eos_token_ids,
                pad_token_id=self.tokenizer.pad_token_id or self.tokenizer.eos_token_id,
            )
        gen_ids = out[0][prompt_tokens:]
        completion_tokens = int(gen_ids.shape[0])
        decoded = self.tokenizer.decode(gen_ids, skip_special_tokens=True)
        clipped, hit = cut_at_stop(decoded, self.stop_text)

        return Generation(
            text=clipped,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            elapsed_seconds=round(time.perf_counter() - started, 6),
            hit_stop=hit,
            finish_reason="stop" if completion_tokens < max_new_tokens else "length",
        )

    def peak_memory_gb(self) -> float | None:
        try:
            if self.torch.cuda.is_available():
                return round(self.torch.cuda.max_memory_allocated() / 1024**3, 2)
        except Exception:  # noqa: BLE001
            return None
        return None
