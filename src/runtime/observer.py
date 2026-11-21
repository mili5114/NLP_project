"""工具观察器：把 task._ns 里的工具函数包一层，计数并记录每次调用尝试。

为什么不去正则数代码文本：代码模式下工具在解释器里被真正调用，
只有包住函数才能按"真实执行顺序"计数，并且覆盖表达式内、循环内、条件分支里的调用。

课程规则：
- 每个 Action 块最多 4 次 listed-tool 调用，整个任务最多 32 次。
- 超限的调用**不执行**，但前面的赋值与其他副作用保留 → 因此包装函数返回 None 而不是抛异常。
- 被拦截的尝试仍然计数（否则循环里的超限调用会无限继续）。
"""

from __future__ import annotations

import functools
import time
from typing import Any, Callable

REPR_LIMIT = 2000


def _clip(text: str, limit: int = REPR_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[Output Truncated]"


def _repr_value(value: Any) -> str:
    try:
        if isinstance(value, str):
            return value
        return repr(value)
    except Exception as exc:  # noqa: BLE001 - repr 失败不能拖垮执行
        return f"<unrepr-able {type(value).__name__}: {exc}>"


class ToolObserver:
    """安装到 Task 上，负责计数、拦截与事件记录。"""

    def __init__(
        self,
        ns: dict[str, Any],
        tool_names: list[str],
        *,
        per_action_limit: int,
        per_task_limit: int,
    ) -> None:
        self.ns = ns
        self.tool_names = list(tool_names)
        self.per_action_limit = per_action_limit
        self.per_task_limit = per_task_limit

        self._originals: dict[str, Callable[..., Any]] = {}
        self._in_tool = False
        self._block_index = 0
        self._block_attempts = 0
        self._task_attempts = 0
        self.executed = 0
        self.blocked = 0
        self.events: list[dict[str, Any]] = []

    # ---- 生命周期 ----
    def install(self) -> None:
        for name in self.tool_names:
            fn = self.ns.get(name)
            if not callable(fn):
                continue
            self._originals[name] = fn
            self.ns[name] = self._wrap(name, fn)

    def start_block(self, block_index: int) -> None:
        self._block_index = block_index
        self._block_attempts = 0
        self.events = []

    @property
    def task_attempts(self) -> int:
        return self._task_attempts

    # ---- 包装 ----
    def _wrap(self, name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
        observer = self

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 工具内部互调不算 listed invocation，也不重复计数
            if observer._in_tool:
                return fn(*args, **kwargs)

            observer._block_attempts += 1
            observer._task_attempts += 1
            index = observer._block_attempts

            over_action = observer._block_attempts > observer.per_action_limit
            over_task = observer._task_attempts > observer.per_task_limit
            args_repr = _clip(", ".join(_repr_value(a) for a in args))
            kwargs_repr = _clip(", ".join(f"{k}={_repr_value(v)}" for k, v in kwargs.items()))

            if over_action or over_task:
                observer.blocked += 1
                reason = (
                    f"blocked: per-action limit {observer.per_action_limit} exceeded"
                    if over_action
                    else f"blocked: per-task limit {observer.per_task_limit} exceeded"
                )
                observer.events.append(
                    {
                        "index": index,
                        "tool": name,
                        "args_repr": args_repr,
                        "kwargs_repr": kwargs_repr,
                        "execution_status": "blocked",
                        "result_repr": None,
                        "error_repr": reason,
                        "elapsed_seconds": 0.0,
                    }
                )
                # 不抛异常：代码块继续，前面已产生的赋值与副作用保留
                return None

            started = time.perf_counter()
            observer._in_tool = True
            try:
                result = fn(*args, **kwargs)
            except BaseException as exc:  # noqa: BLE001 - 工具异常要变成观察，不是崩溃
                elapsed = time.perf_counter() - started
                observer.executed += 1
                observer.events.append(
                    {
                        "index": index,
                        "tool": name,
                        "args_repr": args_repr,
                        "kwargs_repr": kwargs_repr,
                        "execution_status": "error",
                        "result_repr": None,
                        "error_repr": _clip(f"{type(exc).__name__}: {exc}"),
                        "elapsed_seconds": round(elapsed, 6),
                    }
                )
                return None
            else:
                elapsed = time.perf_counter() - started
                observer.executed += 1
                observer.events.append(
                    {
                        "index": index,
                        "tool": name,
                        "args_repr": args_repr,
                        "kwargs_repr": kwargs_repr,
                        "execution_status": "ok",
                        "result_repr": _clip(_repr_value(result)),
                        "error_repr": None,
                        "elapsed_seconds": round(elapsed, 6),
                    }
                )
                return result
            finally:
                observer._in_tool = False

        return wrapper

    # ---- 供记录层使用 ----
    def snapshot(self) -> list[dict[str, Any]]:
        return [dict(e) for e in self.events]
