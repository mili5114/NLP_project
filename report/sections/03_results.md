# Results and analysis — member C draft

Status: STRUCTURE ONLY. No frozen four-condition EVAL has been completed. Replace every `[PENDING]` from the audited EVAL output. This section is delivered to B for report assembly; it does not replace B's method or A's setup section. Keep the overall report within the course page limit.

## Main comparison

We evaluate all 27 held-out tasks per condition, retaining incorrect answers, missing answers, timeouts and budget exhaustion in the denominator. Input and output tokens are summed over every model call within each task before averaging over tasks. Only records matching the frozen code/configuration and passing the completeness/protocol audit enter a result labelled final.

| Condition | Recorded / expected | Success count | Success rate | Mean input tokens/task | Mean output tokens/task | Mean calls/task |
|---|---|---|---|---|---|---|
| A: official output | [PENDING]/27 | [PENDING] | [PENDING] | [PENDING] | [PENDING] | [PENDING] |
| B: Full Trace | [PENDING]/27 | [PENDING] | [PENDING] | [PENDING] | [PENDING] | [PENDING] |
| C: selected feedback method | [PENDING]/27 | [PENDING] | [PENDING] | [PENDING] | [PENDING] | [PENDING] |
| D: matched no-filter ablation | [PENDING]/27 | [PENDING] | [PENDING] | [PENDING] | [PENDING] | [PENDING] |

Source: `condition_summary.csv` and `summary.json` from the same audited batch. Figures: success rate; mean input/output tokens per task. State missing usage counts, termination distributions and audit coverage. Wall time is descriptive because model/hardware and execution overhead matter; GPU resource cost is reported separately using the job ledger.

Do not copy the diagnostic DEV v4 numbers into this table. Do not call one method more efficient solely because it used fewer tokens while failing more tasks. Report success and cost jointly; if accuracy falls, state the trade-off.

## Paired comparisons and attribution

| Pair | Both succeed | C only succeeds | Other condition only succeeds | Both fail | Missing pairs |
|---|---|---|---|---|---|
| C vs B | [PENDING] | [PENDING] | [PENDING] | [PENDING] | [PENDING] |
| C vs D | [PENDING] | [PENDING] | [PENDING] | [PENDING] | [PENDING] |

Source: paired CSV files. Current implementation uses `base=C`, `target=B` or `D`: `base_only` means C alone succeeds; `target_only` means B/D alone succeeds. Token delta is **target minus C**: positive values mean C used fewer tokens. Keep this sign convention in captions.

C vs B measures the overall feedback redesign and may change both organization and filtering. Attribute a filtering effect only to C vs D after confirming the frozen pair differs only in filtering. If filtering never triggers, report that its effect was not exercised. Do not infer significance from a few cases or invent confidence claims.

## Trace evidence: 5–10 paired cases

Select cases after scoring using recorded selection criteria: include a benefit, a regression, a both-success cost difference, a both-failure case and a termination/budget case if present. Categories may overlap; fill the remaining cases with a declared deterministic task order rather than repeatedly choosing visually favorable examples. If a category does not occur, report zero and do not manufacture a case.

| Case ID | task_id | Pair | Outcome category | Turn evidence | Feedback difference | Next-action difference | Interpretation / alternative explanation |
|---|---|---|---|---|---|---|---|
| [PENDING] | [PENDING] | C/B or C/D | [PENDING] | file + turn | [PENDING] | [PENDING] | [PENDING] |

Show the exact model-visible feedback, not the richer observer log, when explaining what information the model received. Separate observed sequence from causal interpretation. Do not expose reference answers in demo inputs.

## Failures, validity and resources

Report failures by termination and scoring reason, including no-answer outcomes. Record the fixed model/upstream/backend/config identities, DEV-only selection and freeze timing; describe any infrastructure recovery and protocol deviations. Preserve noncompliant runs as diagnostic evidence outside the final batch.

Known preparation-stage limitations to revisit: real deadline/context cutoff coverage; same-process execution without a hard sandbox; feedback truncation; small fixed task set; one model/seed. These are limitations to document, not completed proofs. State GPU-hours from all development and formal jobs including failed/aborted active jobs and warmup, with no double counting across ledgers.

## Writing checklist

- [ ] All displayed values trace to one complete audited batch; denominator is 27 per condition.
- [ ] Captions name the frozen method, model and comparison; all placeholders resolved.
- [ ] Main results, paired counts, cases and limitation statements agree.
- [ ] DEV v4 and first-round EVAL are clearly diagnostic, not final evidence.
- [ ] B receives section text, image files, data paths and exact reproduction commands.
