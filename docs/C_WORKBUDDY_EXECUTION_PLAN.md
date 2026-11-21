# 成员 C：WorkBuddy 可执行工作计划

更新：2026-11-21。项目：Project 14 — Execution Feedback and Interaction Efficiency in CodeAct Agents。

## 1. 当前真实状态

- 本地工作区 D:\NLP 尚未 git init，没有 Git remote。无法据此判断其他成员是否在其他位置创建过远程仓库。
- 已有研究方案、三人分工、接口约定、课程配置和三个合成 fixture；尚无真实 runner、评分脚本、正式实验结果。
- 用户负责成员 C：离线评测工具、全部正式 EVAL、结果分析、poster/demo。A 负责平台与 A/B，B 负责 C/D 方法、DEV 选择与冻结，以及最终报告组装。
- 这里的“成员 C”是人员分工，“条件 C”是反馈方法，二者不要混淆。

## 2. 可直接复制给 WorkBuddy 的任务指令

你在本地 D:\NLP 为成员 C 开发 Project 14 的离线评测工具。请实际实现、执行验证并输出文件，不要只给建议。当前阶段完成下文阶段一至三，阶段四以后仅准备入口和交接清单，不启动正式 EVAL。

先阅读工作区适用的 AGENTS.md（如有），然后读 TEAM_ASSIGNMENT.md、docs/interfaces.md、PROJECT14_RESEARCH_PLAN.md、configs/course/Assignment_Attachment.txt、runtime_settings.json、split_manifest.json 和 fixtures。人员职责以 TEAM_ASSIGNMENT.md v2.0 为准；课程限制以原始附件优先。遇到文档矛盾记录到 docs/C_open_questions.md，不擅自修改课程规则。

只负责 C 的模块。不要搭建第二套 CodeAct runner，不下载模型，不实现反馈条件，不替 A/B 跑 DEV，不修改他们的模块和冻结配置。无需 GPU 即可完成现阶段工作。选择 Python 3.10 兼容的轻量实现，评分核心尽量只用标准库，图表依赖单独列出。不要全局安装或更改系统 Python。

把下文 CLI 真正实现到可运行；明确标注合成结果。没有真实日志时不编造实验数字，不把缺失 tokens 填成 0，不假定 A 的 runner 命令已经存在。完成后交付实际运行命令、验证结果、产物路径、已知限制和需要 A/B 提供的内容。

## 3. 仓库建立与协作

### 3.1 先由团队确认唯一远程仓库

请向队友发一句：“我这边 D:\NLP 目前还没初始化 Git，也没有 remote。如果你们已建 GitHub 仓库，把链接发我；没有的话我来建一个，大家统一在这个仓库协作。”

无需等仓库即可开发 C 模块。不要由 WorkBuddy 猜用户名、猜远程 URL、重复创建团队仓库。

如果团队尚未建仓，建议用户创建一个 Private 空仓库并邀请另外两人为 collaborator。公开与否以课程规定和团队决定为准；三人协作的技术工作流无需依赖公开访问。这是协作建议，不是课程要求。

在 GitHub 创建时使用空仓库，避免同时自动生成 README 与本地首个提交冲突。拿到真实 URL 后再配置 remote。若已有远程提交，优先另行 clone，再把本工作区相关文件复制进去并比对，不能强推覆盖。

### 3.2 本地 Git 的执行边界

WorkBuddy 先检查 git status 和 git remote -v。如果仍未初始化，可执行 git init -b main；初始化仅建立本地仓库，不会创建 GitHub 仓库。

先写 .gitignore，再检查 git status。忽略 .venv/、__pycache__/、.pytest_cache/、模型与缓存目录、.env 与凭据、runs/、生成的 results/、本地原始离线答案。保留 src、scripts、tests、合成 fixtures、课程 configs、文档和依赖清单；results 的发布摘要可用明确例外管理。

不要 git add . 后盲目提交。按清单审阅文件；课程原始材料的公开上传由团队根据课程要求决定。真实轨迹较大，应保留本地或另行归档并提供索引，不能因为 gitignore 忽略就视为无需交付。

基础文档进入 main 后，C 使用 c/evaluation-tools 分支；A/B 使用自己的分支。C 的 PR 只包含 C 模块及必要文档。remote 未确认时保留本地成果即可；不要自动 push 或创建远程仓库。

## 4. 阶段一：先把评分器做对（优先交给 A/B）

### 4.1 产物

- src/evaluation/scoring.py：纯函数 score_episode，与现有接口一致。
- src/evaluation/io.py：读写输入、索引和明确错误信息。
- scripts/score.py：离线评分 CLI。
- tests/test_scoring.py：有意义的评分边界测试。
- docs/C_evaluation_usage.md：安装、输入格式、命令、错误行为。
- requirements-evaluation.txt：仅 C 需要的依赖；核心评分可无外部依赖。

### 4.2 输入和命令约定

所有脚本在仓库根目录通过 python scripts/<name>.py 调用即可运行，不能要求临时设置 PYTHONPATH。命令参数错误必须非零退出。

score --episodes 接受单个 episode JSON，或 JSONL 索引。索引每行形如 {"episode_path":"relative/path/episode.json"}，相对路径按索引所在目录解析。也可支持目录扫描，但必须记录实际采用的文件清单，不扫描到旧运行后混在一起。

参考输入使用现有 reference.synthetic.json 的结构：顶层 references 数组，每项 task_id、answer_type、reference。真实参考文件必须从固定上游任务语义导出，类型不能根据预测猜测。由 A 提供该固定版本的离线导出入口或源数据说明，C 负责评分端验证。只读离线文件，不能连接运行中的 agent 或把答案送入 runner。

建议 CLI：

```powershell
python scripts/score.py --episodes fixtures/episode.synthetic.json --references fixtures/reference.synthetic.json --out results/synthetic/scored.jsonl --allow-synthetic
```

### 4.3 评分语义和失败处理

- numeric：使用 Decimal；预测和参考必须是有限数；绝对差 <= Decimal('0.000001') 判正确。拒绝 NaN、Infinity 和无法解析内容。Decimal 运算应避免默认精度导致大数或高精度边界错误，不经过 float 转换。
- string：预测和参考仅 strip 首尾空白，然后精确匹配；不额外小写、不移除标点、不整理内部空格。
- final_answer 为 null 或没有答案：success=false，保留原有终止原因。不能丢弃失败样本。
- answer_type 不认识、参考缺失/重复、episode 结构损坏属于数据错误，应明确报错并非零退出，不能伪装成模型答错。
- 不重新解析整条轨迹来挑一个更正确的答案；评分使用 runner 保存的首个可解析最终答案。
- 输出独立 scored JSONL，保留 episode 原字段，加 success、scoring_reason；不要覆盖在线 episode。
- 正式模式拒绝 synthetic=true 及 SYNTHETIC split。只有显式 --allow-synthetic 可运行合成数据，所有下游输出保留 synthetic 标记。

至少测试：数值完全相同、容差边界内/恰好边界/边界外、负数、科学记数法、高精度、大数、NaN/Infinity、无法解析、字符串首尾空白/内部空格/大小写、null 答案、未知类型、重复和缺失参考、合成保护。测试预期独立写出，不能调用待测函数生成预期。

验收：单元测试通过，现有合成 episode 得到 success=true；改用明确错误的合成预测可得到 false；输入错误以非零退出。此时立即将 CLI、输入格式和示例发给 A/B，让他们自己评分 DEV，不必等待图表模块完成。

## 5. 阶段二：完整性审计与统计

### 5.1 产物

- src/evaluation/audit.py、aggregation.py。
- scripts/audit_results.py、summarize.py。
- tests/test_audit.py、test_aggregation.py。
- fixtures/evaluation/：最小成功、失败、缺失、重复、token 不一致等合成数据及轨迹；全部显式 synthetic。

### 5.2 统一命令

```powershell
python scripts/audit_results.py --episodes <index.jsonl> --split DEV --conditions A B --out <audit.json>
python scripts/summarize.py --scored <scored.jsonl> --split DEV --conditions A B --out-dir <summary-directory>
```

正式 EVAL 改为 --split EVAL --conditions A B C D；预期集合直接读取 configs/course/split_manifest.json。合成模式使用单独 --allow-synthetic 和显式合成期望任务清单，不把 synthetic 任务塞进官方 manifest。

### 5.3 审计必须覆盖

1. 精确集合：DEV 为 16×指定条件，EVAL 为 27×4；检查缺失、重复、未知 task_id、错误 split、未知 condition、不同 run 混入。
2. 无答案、超时、预算耗尽是有记录的实验失败，和“没有 episode 文件”区分。缺失文件使正式结果不完整，不能用成功率分母缩小掩盖。
3. 每个 episode 的 trajectory_path 可解析；JSONL 每行合法；实际模型调用数与 model_calls 一致；每调用 input/output tokens 非负整数，并与 episode 总量一致。最终回答调用计入。
4. 查验原始生成、模型输入、代码/工具事件、Python 输出、可见反馈、最终答案相关证据。区分字段不存在与合法空值。
5. 根据 runtime_settings.json 审计可见反馈长度、token/工具预算等可核验限制；发现超限记录证据，不能擅自截掉或改写日志。耗时存在测量开销时作为带解释的异常，不自动删除样本。
6. 检查 manifest/episode 版本、配置 hash、一致性与 synthetic 污染。完整性不足时输出清晰状态和非零退出，仍保存审计报告。
7. 输出 error/warning、文件路径、task/condition、修复责任人提示。平台/在线字段问题归 A，方法/冻结配置归 B，离线工具问题归 C。

现有接口对 turns.jsonl 只列了语义，没有逐字段 schema。C 可以为合成测试编写一套明确的最小结构并文档化；真实 A 日志通过单独 reader/adapter 适配。不要把自定合成字段声称为 A 已承诺的最终结构，也不要静默兼容所有拼写、填默认值。接真实日志时只需一次明确字段映射。

### 5.4 统计口径

- 逐任务 CSV：task_id、condition、success、termination_reason、input/output tokens、model/tool counts、wall_seconds、run_id、证据路径。
- 主表每条件：N_expected、N_recorded、N_scored、success_count、success_rate、mean_input_tokens、mean_output_tokens、mean_model_calls、mean_wall_seconds。
- 正式完整 EVAL 每条件分母 27，所有有效失败样本计入。缺失样本不得伪造失败轨迹；未完整时标 INCOMPLETE，不输出可被误用为正式结论的完整主表。
- 先对每任务汇总所有模型调用，再对任务求均值；不把每轮 tokens 直接平均。不将缺失 usage 当作 0。
- 配对比较按 task_id 对齐，输出 C vs B 和 C vs D 的双方成功、C独有成功、对方独有成功、双方失败及 tokens 差值。
- 只有 C vs D 在既定设计中隔离筛选；C vs B 同时改变排序和筛选，不能单独归因筛选。
- 不将 wall_seconds 自动当 GPU hours。资源账目保留硬件、时间段、GPU 数、占用/计量方法；共享时间段避免重复计数。分开报告已计量值与未知值。

验收：构造缺失/重复/错误 split/usage 缺失/总量不一致，审计应准确发现；构造小型已知结果，统计手工可核对。重复运行输出稳定，正式模式不会摄入合成样本。

## 6. 阶段三：图表、交接与 C 的个人证据

### 6.1 产物

- scripts/plot_results.py：从统计表生成成功率图、平均输入/输出 tokens 图、配对变化图，支持 PNG/PDF；不要硬编码结果。
- results/synthetic/ 下可复现的演示结果；标题和图中清楚标 SYNTHETIC — NOT EXPERIMENTAL RESULTS。
- docs/C_handoff.md：给 A/B 的安装方式、CLI、最小输入、版本、已通过的检查、缺陷反馈格式。
- docs/contributions/C.md：实际完成模块、关键决策、验证命令、本人代码文件；只记已完成内容。
- docs/C_eval_readiness.md：正式 EVAL 开始前清单与尚缺项。

使用小型 synthetic 端到端运行验证 scorer → auditor → summary → plots。图表导出后检查可读性、标签、数字与表格一致；这不是正式实验结果。

C 面试准备可围绕：Decimal 边界为何这样判、失败分母、按任务聚合 tokens、重复/缺失检测、数据泄漏隔离、配对消融解释。每人理解完整项目，但 C 有明确独立代码贡献。

## 7. 阶段四：收到冻结包后才执行正式 EVAL

### 7.1 A/B 必须交给 C

- A：真实 episode + turns + manifest 样例、字段说明、可用环境/硬件、固定版本 runner、运行命令与在线答案隔离证据。
- B：团队代码 commit、A/B/C/D 配置和 hash、课程附件 hash、模型/tokenizer revision、统一后端及依赖版本、DEV 候选与选择记录、冻结时间、四条件命令、预计资源。
- A/B 各自 DEV 的评分结果与 GPU 账目。C 汇总账目，不接管他们的 DEV 清理与重跑。
- 用真实 DEV 已有日志测试 C 读取器与统计端；字段不一致由 owner 修复或 C 写离线适配层，不改变研究方法。

### 7.2 执行顺序

1. 验证 freeze commit/config hash、环境和课程设置；建立 EVAL 执行索引，预期 108 个唯一 task-condition 槽位。
2. 先用已有 DEV 做流程健康检查；正式 EVAL 的最先几个槽位可先审计日志，若健康直接纳入同一次正式运行，不按正确率决定是否重来。
3. 默认顺序执行或使用 A 已验证的调度方式。并发数按显存和服务能力确定，不能因为任务180秒上限就估算出整个项目实际用时。
4. 保存原始记录，再离线评分、审计。记录每次尝试和执行原因。模型答错、无答案、预算耗尽均不重跑到成功。
5. 若基础设施故障导致有效尝试无法完成，保留原始故障记录，按预先写明的恢复规则处理；方法或 runner 修复必须记录新 commit/config 与受影响范围，不能静默替换结果。
6. EVAL 不参与阈值选择或方法调参。不因看到 EVAL 成败改反馈规则。
7. 108 槽位完整且审计通过后生成正式主表、配对表和图。

实际 runner 调用必须抄自 A/B 的 frozen_run.md；此时不虚构 python run_eval.py 等不存在的命令。若需要批量启动脚本，C 只包装已有 runner 并记录状态，不重写推理与执行逻辑。

## 8. 阶段五：研究分析与最终交付

- 5–10 个配对案例，若可用证据足够：给 task/condition、原始轨迹路径、关键调用与反馈、之后行为变化、结果及解释。包括成功、失败和没有改善的案例，不能只展示好例子。
- report/sections/results_analysis.md：实验主表、成本、C/B与C/D、错误类型、局限；交 B 合并六页以内正文报告。
- report/poster.*：依据真实数据完成整张 poster，版式参考课程示例；日期、尺寸及展示规则待课程确认。
- report/demo/：同任务不同反馈条件的演示脚本与证据，准备可回放轨迹/录屏方案；录屏是否获准尚待 TA 确认，不把录屏已被允许当事实。
- runs/eval/ 原始日志与预测、results/per_task.csv、主表/图、audit.json、资源账目、个人贡献记录、复现命令、归档索引及校验值。
- B 交最终报告 PDF；C 负责自己的结果章节与展示产物，不重复排整篇报告。

## 9. 时间与依赖：按工作日安排，不是课程截止日期

| 节点 | C 的工作 | 完成标准 | 依赖 |
|---|---|---|---|
| 第1工作日 | 阅读、核心评分、边界测试 | 合成示例可评分，错误输入正确退出 | 无需 A/B/GPU |
| 第2工作日 | CLI、输入文档、交 A/B scorer v1 | 队友能按一条命令使用 | 无需真实实验 |
| 第3–4工作日 | 审计、聚合、配对与测试 | 缺失/重复/usage问题可检出 | 官方名单、合成日志 |
| 第5工作日 | 图表、端到端演示、交接 | 可复现且合成标记清楚 | 自己工具链 |
| A真实日志到达后 | 明确一次字段适配 | 真实DEV日志可读可审计 | A |
| B冻结包到达后 | 全量EVAL和审计 | 108槽位、完整原始证据 | A平台+B冻结+GPU |
| EVAL完成后约2–3工作日 | 案例/结果章节/海报/demo | 真数据产物交 B/提交人 | 正式结果 |

真实课程截止日期尚未在本计划确定，拿到后倒排；不能把这些工作日当学校要求的日期。

## 10. WorkBuddy 的最终回报格式

1. 已实现文件与简要用途。
2. 实际执行的安装/测试/合成端到端命令和结果，不把“建议执行”写成“已通过”。
3. scorer 现在能否交给 A/B，以及一条可复制命令。
4. 真实 EVAL 尚缺的明确内容及 owner。
5. Git 当前分支、是否有 remote、是否有未提交文件；没有远程就直说。
6. 本轮未开展真实推理/正式 EVAL，所有演示结果标记 synthetic。

完成阶段一至三后停在交接点；不等待 GPU、不擅自开发 A/B 模块、不伪造实验结果。若有可继续修复的自身工具问题，先修好再汇报。
