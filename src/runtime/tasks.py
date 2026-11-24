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
import inspect
import io
import re
import sys
from pathlib import Path
from typing import Any

from .config import CourseConfig, repo_root

# 课程附件 §3：提示里的工具签名必须与真实函数一致。
# 上游 m3tooleval 的 fn_metadata 与函数定义不符（find_flights 少一个参数、
# reverse_string/string_length 参数名不是 s），在加载适配层统一改写，
# third_party 原始文件保持不动，改动可追溯到这里。
_COURSE_SIGNATURE_PARAMS: dict[str, str] = {
    "find_flights": "from_location: str, to_location: str, date: str",
    "reverse_string": "s: str",
    "string_length": "s: str",
}
_SIGNATURE_RE = re.compile(r"\b(find_flights|reverse_string|string_length)\s*\(([^)]*)\)")


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


def _verify_signature_matches_function(name: str, fn_signature: str, function: Any) -> None:
    """改写后的提示签名必须与真实函数的参数名逐一对应，否则直接报错。"""
    m = re.match(rf"{re.escape(name)}\s*\(([^)]*)\)", fn_signature.strip())
    prompted = [p.split(":")[0].strip() for p in m.group(1).split(",")] if m and m.group(1).strip() else []
    actual = list(inspect.signature(function).parameters)
    if prompted != actual:
        raise RuntimeError(
            f"{name} 的提示签名 {fn_signature!r} 与真实函数参数 {actual} 不一致（课程附件 §3）"
        )


def _apply_course_signatures(task: Any) -> None:
    """把 task.tools 里三个工具的 fn_signature 改成附件 §3 要求的形式。

    带类型注释和不含注释的变体都覆盖；改写后与真实函数签名核对。
    """
    changed = False
    tools: dict[str, Any] = {}
    for tool_name, tool in task.tools.items():
        sig = tool.fn_signature or ""
        if _SIGNATURE_RE.search(sig):
            new_sig = _SIGNATURE_RE.sub(
                lambda m: f"{m.group(1)}({_COURSE_SIGNATURE_PARAMS[m.group(1)]})", sig
            )
            _verify_signature_matches_function(tool_name, new_sig, tool.function)
            if new_sig != sig:
                tool = tool._replace(fn_signature=new_sig)
                changed = True
        tools[tool_name] = tool
    if changed:
        task.tools = tools


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
    result = {t.name: t for t in tasks}
    for task in result.values():
        _apply_course_signatures(task)
    return result


def get_task(task_id: str) -> Any:
    module_name = module_of(task_id)
    tasks = load_tasks(module_name)
    if task_id not in tasks:
        known = ", ".join(sorted(tasks)[:5])
        raise KeyError(f"{task_id} 不在 {module_name} 里；现有示例：{known} …")
    return tasks[task_id]


def task_names_in_module(module_name: str) -> list[str]:
    return sorted(load_tasks(module_name, reload=False))
