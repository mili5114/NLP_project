"""反馈层。目录内文件按 `docs/interfaces.md` §1 分属两人，同一文件只有一个 Owner。

- baselines.py  （A）条件 A：官方输出；条件 B：Full Trace
- selective.py  （B）条件 C/D 的筛选规则
- renderers.py  （B）C/D 共用的 renderer 与截断

统一入口（A 实现 dispatch，B 只提供 C/D 分支）：

    build_feedback(*, python_output: str, events: list[dict],
                   condition: str, settings: dict) -> {"text": str, "metadata": dict}

约束：text 不超过 2000 字符（含截断标记）；不顺带把 metadata 发给模型；
函数内不得再次执行工具、不得改事件对象或解释器状态；输入不含标准答案。
"""
