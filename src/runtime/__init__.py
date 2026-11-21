"""A 侧运行时：模型后端、runner、预算与状态机、工具事件观察器。

计划模块（尚未实现，接口见 docs/interfaces.md）：

- backend.py   Backend.generate(messages, max_tokens, settings) -> text, usage, seconds
- runner.py    单 episode 状态机：轮次/token/时间/工具预算、首个 Answer 即停、最终回答轮
- executor.py  每任务新建解释器与 web tools，任务内变量保留，任务间重置
- observer.py  在 task._ns 上包一层，产出 7 字段工具事件（ok/error/blocked）
- budget.py    12+1 轮、3072 tokens、16384 context、180s/15s 上限的裁定逻辑

不在此目录放反馈内容规则（A/B 在 src/feedback/baselines.py，C/D 归 B）。
"""
