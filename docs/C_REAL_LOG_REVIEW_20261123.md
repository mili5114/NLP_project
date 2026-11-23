# C：真实 DEV 日志对接与协议核验

审查日期：2026-11-23。输入仓库 main：`38198ea`。本轮不读取离线标准答案，不计算正确率，不处理 EVAL 轨迹，不修改原始记录或 A/B 模块。

## 完成的工作

- 新增 `src/evaluation/runtime_adapter.py`，显式适配 A 的 runtime schema `1`：0-based turn_index 转为 1-based；`parsed.type=answer` 映射 produced_final_answer；`generation_settings.is_final_turn` 单独映射 final-only；raw_text/tool_events/feedback_text 映射离线字段。
- 从相邻 manifest 的 team_commit/model.revision 读取版本；不伪造 episode 缺失字段。保留原字段、原路径和三个源文件的 SHA-256。
- 新增 `scripts/prepare_runtime_records.py`，只选择 DEV A/B；明确排除已登记的旧 pilot_14051965。派生数据保存在 results 中，不覆盖源文件。
- 32/32 唯一任务条件齐全；逐轮 input/output tokens 和模型调用数与 episode 一致；有答案时仅有一个 answer-producing 调用且处于最后。
- 本轮属于结构核验，**不是正式协议认证或完整审计 PASS**。不以是否有答案代替评分正确性。

## 运行方法

在仓库根目录执行，输出目录必须是新目录：

```powershell
python scripts/prepare_runtime_records.py --out-dir results/dev_adapter_review
```

该命令写出派生 episode/turns、index.jsonl 和 preflight.json。退出码 0 仅表示当前有限检查无发现，1 表示存在缺失或协议待办，2 表示输入损坏/不支持。当前真实 DEV 运行返回 **1**，不能声称全部审计通过。原始目录里的旧 pilot 不进入 32 槽位。

## 已发现的阻碍（A 负责运行器，C 提供证据）

| 问题 | DEV 受影响记录 | 证据与处理 |
|---|---:|---|
| find_flights 提示仍为 destination/date 两参数 | 8 | 真实 system prompt 中 `Signature: find_flights(destination: str, date: str)`；附件 §3 要求 from_location/to_location/date。参数带类型注释时也检查，不能只匹配无注释字符串。 |
| reverse_string 参数仍非 s | 6 | 对应 message_decoder 任务的首轮 system prompt；附件 §3 要求 s。 |
| string_length 参数仍非 s | 6 | 同上，与前行任务重合，不应把三个数量相加当独立任务数。 |
| token 预算出口没有使用预留最终轮 | 2 | DEV A/B 的 trade_calculator/optimizing_bulk_purchase_discounts；终止 token_budget_exhausted，但仍有生成预算、没有 final-only 轮。A 检查 runner 的 alloc<=0 分支是否绕开最终轮，并验证时间/上下文是否允许。 |

`docs/failure_taxonomy.md` 将签名不匹配称为天然任务陷阱，但课程附件明确要求先修正这些提示。应先解决课程协议问题，再讨论反馈方法效果；不能将应修未修的提示作为方法收益来源。

C 不替 A 修 runner，也不擅自重跑。A 修复后记录新版本、受影响范围和旧数据用途；是否保留首轮数据为诊断材料、如何重新建立一致基线需团队统一记录。严禁无记录覆盖旧数据。

## 尚不能直接用于冻结后正式比较的原因

1. 目前 config_sha256 等于课程 runtime_settings.json 的 hash，不是完整 condition 配置 hash；适配器明确标记 scope，不将其包装成完整 freeze。
2. 尚未发现 B 的 C/D 插件、DEV 选择登记与冻结包。本轮未开展 C/D 或正式全条件 EVAL。
3. 仓库已有 54 条首轮 EVAL A/B 日志。它们的存在不证明冻结后正式实验完成，需核验生成时间、代码版本、协议与冻结关系；B 不应利用 EVAL 结果选择方法。C 本轮只用 DEV 定位问题。
4. 工具拦截需区分实际执行和 blocked 尝试。C 旧审计器将事件数直接与4/32比较，遇到合法记录的超额 blocked 时可能误报；后续需修正该规则，当前不将它的报错全归于 A。
5. 上下文、硬时间限制、参考答案环境隔离、工具完整返回证据及依赖/模型 provenance 还需独立检查。本轮未证明这些均满足。
6. 尚无真实离线 reference 导出交接；不根据任务文字自行编造标准答案，也不把有最终答案等同正确。

## 下一次交接

- A：确认提示修正、预留最终轮出口；提供修复版本及一个真实 DEV episode/turns/manifest，再完成相同版本的 DEV 基线；提供固定上游的私有离线 reference 导出或导出入口。
- B：只用 DEV，提交候选选择记录、C/D 方法配置和冻结说明。
- C：继续完善 blocked 语义审计和正式 provenance 校验；收到 reference 后评分。原 DEV 评分仍由 A/B 自行调用 C 的 CLI，C 负责对接验证，不接管全部 DEV 实验。
