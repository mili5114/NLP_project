"""预算状态机。

所有数字都来自 configs/course/runtime_settings.json 的 limits，不在这里写死。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TurnBudget:
    max_new_tokens: int
    remaining_generated: int
    remaining_context: int
    is_final: bool


@dataclass
class Budget:
    limits: Any  # config.Limits
    turns_used: int = 0
    generated_tokens: int = 0
    started_at: float = field(default_factory=time.monotonic)
    final_turn_used: bool = False

    # ---- 时间 ----
    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def task_expired(self) -> bool:
        return self.elapsed_seconds >= self.limits.task_seconds

    # ---- 轮次 ----
    @property
    def turns_left(self) -> int:
        return max(0, self.limits.interaction_turns - self.turns_used)

    def can_start_turn(self) -> bool:
        return self.turns_left > 0 and not self.task_expired and self.remaining_generated > 0

    # ---- token ----
    @property
    def remaining_generated(self) -> int:
        return max(0, self.limits.total_generated_tokens - self.generated_tokens)

    def allocate(self, *, prompt_tokens: int, is_final: bool = False) -> TurnBudget:
        """给这一轮分配生成长度。

        交互轮：min(tokens_per_interaction, 剩余 - final_answer_tokens)
          —— 始终为最后那次纯回答预留 128 token，避免把预算跑干、连答案都写不完。
        最终轮：min(final_answer_tokens, 剩余)。
        """
        if is_final:
            budget = min(self.limits.final_answer_tokens, self.remaining_generated)
        else:
            reserve = self.limits.final_answer_tokens
            budget = min(self.limits.tokens_per_interaction, max(0, self.remaining_generated - reserve))

        remaining_context = max(0, self.limits.context_tokens - prompt_tokens)
        budget = min(budget, remaining_context)
        return TurnBudget(
            max_new_tokens=max(0, budget),
            remaining_generated=self.remaining_generated,
            remaining_context=remaining_context,
            is_final=is_final,
        )

    def charge(self, *, completion_tokens: int, is_final: bool = False) -> None:
        self.generated_tokens += max(0, completion_tokens)
        if is_final:
            self.final_turn_used = True
        else:
            self.turns_used += 1

    # ---- 记录用 ----
    def snapshot(self) -> dict[str, Any]:
        return {
            "turns_used": self.turns_used,
            "turns_left": self.turns_left,
            "generated_tokens": self.generated_tokens,
            "remaining_generated": self.remaining_generated,
            "final_turn_used": self.final_turn_used,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
        }
