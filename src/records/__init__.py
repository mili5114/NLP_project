"""A 侧记录层：manifest / turns.jsonl / episode 三件套的 schema 与序列化。

字段定义见 docs/interfaces.md §3。要求：

- 每行一次模型调用，含实际 messages、生成设置、原始文本、解析结果、code、events、
  python 原始输出、模型可见反馈、feedback_metadata、真实 tokens、耗时、预算余量。
- 在线记录**不含** reference_answer / success；正确性由 C 的离线 scorer 填。
- 路径用安全 slug，原始 task_id 保留在字段里（task 名含 `/`）。
- 配置 hash、版本、token 统计一律来自实际运行，不复制 fixture 数字。
"""
