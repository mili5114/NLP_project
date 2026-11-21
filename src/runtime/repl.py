"""Action 块执行器。

与上游 `tasks/repl.py` 的差异（两处，都是为了记录口径）：
1. **不截断输出**。上游把 Python 输出切到 2000 字符再返回，记录层就拿不到原始观察，
   而课程要求 2000 字符上限体现在“模型可见反馈”上，由反馈层做，不在执行层做。
2. **超时可关闭**。`signal.SIGALRM` 只在 Unix 主线程可用；本机 Windows 上退化
   （不中断，只在结果里标 timed_out），集群上才是真的 15 秒硬限。
"""

from __future__ import annotations

import signal
import threading
import time
from contextlib import contextmanager
from typing import Any


class BlockExecutor:
    """在一个持久的命名空间里执行代码块，变量跨块保留。"""

    def __init__(self, user_ns: dict[str, Any], timeout_seconds: float) -> None:
        from IPython.core.interactiveshell import InteractiveShell

        self.timeout_seconds = float(timeout_seconds)
        self.shell = InteractiveShell(
            user_ns=dict(user_ns),
            colors="NoColor",
        )
        # 同上：包装后的工具函数在 dict 里，浅拷贝即可共享引用
        self.shell.user_ns.update(user_ns)

    # ---- 超时 ----
    @staticmethod
    def _supports_alarm() -> bool:
        return hasattr(signal, "SIGALRM") and threading.current_thread() is threading.main_thread()

    @contextmanager
    def _time_limit(self):
        """返回一个可读标记：True 表示确实被 alarm 中断。"""
        flag = {"timed_out": False}
        if not self._supports_alarm():
            yield flag
            return

        def handler(signum, frame):  # noqa: ANN001, ARG001
            flag["timed_out"] = True
            raise TimeoutError(f"Timed out after {self.timeout_seconds:g} seconds.")

        old = signal.signal(signal.SIGALRM, handler)
        signal.setitimer(signal.ITIMER_REAL, self.timeout_seconds)
        try:
            yield flag
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old)

    # ---- 执行 ----
    def run(self, code: str) -> dict[str, Any]:
        from IPython.utils import io

        started = time.perf_counter()
        timed_out = False
        error_repr: str | None = None
        stdout = ""

        try:
            with self._time_limit() as flag, io.capture_output() as captured:
                result = self.shell.run_cell(code, store_history=False)
                stdout = captured.stdout
            timed_out = bool(flag["timed_out"])
            exc = getattr(result, "error_before_exec", None) or getattr(result, "error_in_exec", None)
            if exc is not None:
                error_repr = f"{type(exc).__name__}: {exc}"
        except TimeoutError as exc:
            timed_out = True
            error_repr = f"TimeoutError: {exc}"
            try:
                stdout = captured.stdout  # type: ignore[possibly-undefined]
            except Exception:  # noqa: BLE001
                stdout = ""
        except BaseException as exc:  # noqa: BLE001
            error_repr = f"{type(exc).__name__}: {exc}"

        elapsed = time.perf_counter() - started
        if stdout == "":
            stdout = "[Executed Successfully with No Output, Did you forget to print?]"

        return {
            "stdout": stdout,
            "error_repr": error_repr,
            "timed_out": timed_out,
            "elapsed_seconds": round(elapsed, 6),
        }

    def reset(self) -> None:
        """任务间重置：变量与导入全部丢弃。"""
        self.shell.reset(new_session=True)
