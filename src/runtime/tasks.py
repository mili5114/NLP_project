"""上游任务适配层。

两个必须处理的坑：
1. `Task.__init__` 会 `print_task()`，把 `expected_output` 打到 stdout —— 这就是答案泄漏点。
   这里把 stdout 全部重定向并丢弃，验证运行时不留下任何痕迹（tests 里有断言）。
2. web_browsing 等模块的 tools 是 callable，每次调用生成带状态的 browser 实例。
   若复用同一个 Task，状态会跨 episode 污染，所以每个 episode 都 reload 模块重新构造。
"""

from __future__ import annotations

import contextlib
import importlib
import io
import sys
from pathlib import Path
from typing import Any

from .config import CourseConfig, repo_root


def upstream_eval_dir(cfg: CourseConfig | None = None) -> Path:
    return repo_root() / "third_party" / "code-act" / "scripts" / "eval"


def ensure_importable(cfg: CourseConfig | None = None) -> Path:
    path = str(upstream_eval_dir(cfg))
    if path not in sys.path:
        sys.path.insert(0, path)
    return Path(path)


def action_mode() -> Any:
    ensure_importable()
    from m3tooleval.tasks.base import ActionMode  # noqa: PLC0415

    return ActionMode.CODE_AS_ACTION


def module_of(task_id: str) -> str:
    if "/" not in task_id:
        raise ValueError(f"task_id 需要 `<module>/<task>` 形式，收到 {task_id!r}")
    return task_id.split("/", 1)[0]


def load_tasks(module_name: str, *, reload: bool = True) -> dict[str, Any]:
    """导入（或重新导入）一个任务模块，返回 {task_id: Task}。

    重定向 stdout 是为了吞掉 `print_task()` 打出的标准答案；
    返回前不保留该缓冲区内容，也不写入任何日志。
    """
    ensure_importable()
    name = f"m3tooleval.tasks.impl.{module_name}"
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        module = importlib.import_module(name)
        if reload:
            module = importlib.reload(module)
    tasks = getattr(module, "TASKS", None)
    if not tasks:
        raise RuntimeError(f"模块 {module_name} 没有 TASKS")
    return {t.name: t for t in tasks}


def get_task(task_id: str) -> Any:
    module_name = module_of(task_id)
    tasks = load_tasks(module_name)
    if task_id not in tasks:
        known = ", ".join(sorted(tasks)[:5])
        raise KeyError(f"{task_id} 不在 {module_name} 里；现有示例：{known} …")
    return tasks[task_id]


def task_names_in_module(module_name: str) -> list[str]:
    return sorted(load_tasks(module_name, reload=False))
