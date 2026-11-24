"""Episode 主循环。

与上游 `main.py` 的关键差异（都是课程要求）：
- 首个可解析的 `Answer:` 立即结束，不再拿标准答案判断对错、也不回 "Your answer is incorrect"。
- 12 轮交互用尽后，追加**一次**只能回答、不能执行工具的最终轮。
- 工具调用由 observer 计数并在超限时拦截，不靠数代码文本。
- 标准答案从不进入 messages、不进入 feedback、不写入在线记录。
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from ..feedback.dispatcher import build_feedback
from ..records.writer import EpisodeWriter
from .budget import Budget
from .config import CourseConfig, repo_root, safe_slug
from .observer import ToolObserver
from .repl import BlockExecutor
from .tasks import action_mode, get_task


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root()),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def _count_tokens(backend: Any, messages: list[dict[str, str]]) -> int:
    fn = getattr(backend, "count_tokens", None)
    if callable(fn):
        return int(fn(messages))
    # 没有 tokenizer 的假后端：按字符粗估，只影响 budget 分配，不影响真实统计
    return sum(len(m.get("content", "")) for m in messages) // 4


def build_system_prompt(task: Any, cfg: CourseConfig) -> str:
    return task.get_prompt(action_mode()) + cfg.initial_contract


def feedback_settings(cfg: CourseConfig) -> dict[str, Any]:
    limits = cfg.limits
    return {
        "feedback_characters": limits.feedback_characters,
        "truncation_marker": cfg.truncation_marker,
        "full_trace_format": cfg.full_trace_format,
        "stop_text": cfg.stop_text,
    }


def run_episode(
    *,
    task_id: str,
    condition: str,
    cfg: CourseConfig,
    backend: Any,
    runs_root: Path | str,
    split: str = "DEV",
    seed: int | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    condition = condition.upper()
    limits = cfg.limits
    seed = int(seed if seed is not None else cfg.model["seed"])
    run_id = run_id or f"{split}-{condition}-{safe_slug(task_id)}-s{seed}"

    task = get_task(task_id)
    settings = feedback_settings(cfg)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": build_system_prompt(task, cfg)}
    ]

    observer = ToolObserver(
        task._ns,
        list(task.tools),
        per_action_limit=limits.tool_attempts_per_action,
        per_task_limit=limits.tool_attempts_per_task,
    )
    observer.install()
    repl = BlockExecutor(task._ns, limits.action_seconds)
    budget = Budget(limits)

    manifest = {
        "run_id": run_id,
        "split": split,
        "condition": condition,
        "seed": seed,
        "task_id": task_id,
        "tasks": [task_id],
        "model": cfg.model,
        "backend": getattr(backend, "name", type(backend).__name__),
        "upstream_commit": cfg.code_commit,
        "team_commit": _git_head(),
        "course_hashes": cfg.hashes,
        "limits": {
            "interaction_turns": limits.interaction_turns,
            "tokens_per_interaction": limits.tokens_per_interaction,
            "final_answer_tokens": limits.final_answer_tokens,
            "total_generated_tokens": limits.total_generated_tokens,
            "context_tokens": limits.context_tokens,
            "tool_attempts_per_action": limits.tool_attempts_per_action,
            "tool_attempts_per_task": limits.tool_attempts_per_task,
            "task_seconds": limits.task_seconds,
            "action_seconds": limits.action_seconds,
            "feedback_characters": limits.feedback_characters,
        },
        "stop_text": cfg.stop_text,
    }

    writer = EpisodeWriter(
        Path(runs_root),
        run_id=run_id,
        slug=safe_slug(f"{task_id}__{run_id}"),
        split=split,
        condition=condition,
        manifest=manifest,
    )
    writer.open()

    total_input_tokens = 0
    total_output_tokens = 0
    model_calls = 0
    termination: str | None = None
    final_answer: str | None = None
    turn_index = 0

    def _record_turn(
        *,
        snapshot: list[dict[str, str]],
        gen: Any,
        parsed: dict[str, Any],
        max_new_tokens: int,
        action: str | None,
        events: list[dict[str, Any]],
        python_output: str | None,
        feedback_text: str | None,
        feedback_metadata: dict[str, Any] | None,
        is_final: bool,
        exec_seconds: float = 0.0,
    ) -> None:
        nonlocal total_input_tokens, total_output_tokens, model_calls
        total_input_tokens += int(gen.prompt_tokens)
        total_output_tokens += int(gen.completion_tokens)
        model_calls += 1
        writer.write_turn(
            {
                "messages": snapshot,
                "generation_settings": {
                    "max_new_tokens": max_new_tokens,
                    "do_sample": False,
                    "enable_thinking": False,
                    "stop_text": cfg.stop_text,
                    "is_final_turn": is_final,
                },
                "raw_text": gen.text,
                "parsed": parsed,
                "action": action,
                "tool_events": events,
                "python_output": python_output,
                "feedback_text": feedback_text,
                "feedback_metadata": feedback_metadata,
                "input_tokens": int(gen.prompt_tokens),
                "output_tokens": int(gen.completion_tokens),
                "elapsed_seconds": round(float(gen.elapsed_seconds) + exec_seconds, 6),
                "budget": budget.snapshot(),
            }
        )

    # ---------- 交互轮 ----------
    while True:
        if budget.task_expired:
            termination = "task_timeout"
            break
        if not budget.can_start_turn():
            break

        snapshot = [dict(m) for m in messages]
        prompt_tokens = _count_tokens(backend, messages)
        alloc = budget.allocate(prompt_tokens=prompt_tokens)
        if alloc.max_new_tokens <= 0:
            # 交互轮分不到生成预算（生成预算只剩为最终轮预留的 128，或上下文已满）：
            # 不在这里判 token_budget_exhausted，而是跳出循环、带着预留预算进最终轮
            # （课程附件 §2：交互轮始终为最终答案预留 128 token）。
            break

        gen = backend.generate(messages, max_new_tokens=alloc.max_new_tokens)
        budget.charge(completion_tokens=gen.completion_tokens)
        parsed = task.parse_generation(gen.text)
        turn_index += 1

        if parsed["type"] == "answer":
            final_answer = parsed["content"]
            termination = "answer"
            _record_turn(
                snapshot=snapshot,
                gen=gen,
                parsed=parsed,
                max_new_tokens=alloc.max_new_tokens,
                action=None,
                events=[],
                python_output=None,
                feedback_text=None,
                feedback_metadata=None,
                is_final=False,
            )
            break

        if parsed["type"] == "action":
            observer.start_block(turn_index)
            result = repl.run(parsed["content"])
            events = observer.snapshot()
            fb = build_feedback(
                python_output=result["stdout"],
                events=events,
                condition=condition,
                settings=settings,
            )
            messages.append({"role": "assistant", "content": gen.text})
            messages.append({"role": "user", "content": fb["text"]})
            _record_turn(
                snapshot=snapshot,
                gen=gen,
                parsed=parsed,
                max_new_tokens=alloc.max_new_tokens,
                action=parsed["content"],
                events=events,
                python_output=result["stdout"],
                feedback_text=fb["text"],
                feedback_metadata=fb["metadata"],
                is_final=False,
                exec_seconds=result["elapsed_seconds"],
            )
            if result["timed_out"]:
                termination = "action_timeout"
                break
            continue

        # invalid：不执行任何东西，把提示原样送回
        messages.append({"role": "assistant", "content": gen.text})
        messages.append({"role": "user", "content": parsed["content"]})
        _record_turn(
            snapshot=snapshot,
            gen=gen,
            parsed=parsed,
            max_new_tokens=alloc.max_new_tokens,
            action=None,
            events=[],
            python_output=None,
            feedback_text=parsed["content"],
            feedback_metadata={"note": "invalid_generation"},
            is_final=False,
        )

    # ---------- 最终轮（仅当交互阶段结束时还没有 termination：轮次/token/上下文耗尽） ----------
    if termination is None:
        if budget.task_expired:
            # 时间上限在最后一轮执行后到期：时间耗尽不允许再请求模型。
            termination = "task_timeout"
        else:
            exhausted_by = "turns" if budget.turns_left == 0 else "tokens"
            messages.append({"role": "user", "content": cfg.final_answer_request})
            snapshot = [dict(m) for m in messages]
            prompt_tokens = _count_tokens(backend, messages)
            alloc = budget.allocate(prompt_tokens=prompt_tokens, is_final=True)

            if alloc.max_new_tokens > 0:
                gen = backend.generate(messages, max_new_tokens=alloc.max_new_tokens)
                budget.charge(completion_tokens=gen.completion_tokens, is_final=True)
                parsed = task.parse_generation(gen.text)
                if parsed["type"] == "answer":
                    final_answer = parsed["content"]
                    termination = f"final_answer_after_{exhausted_by}_exhausted"
                else:
                    termination = f"no_answer_after_{exhausted_by}_exhausted"
                _record_turn(
                    snapshot=snapshot,
                    gen=gen,
                    parsed=parsed,
                    max_new_tokens=alloc.max_new_tokens,
                    action=None,
                    events=[],
                    python_output=None,
                    feedback_text=None,
                    feedback_metadata={"note": "final_answer_only_turn"},
                    is_final=True,
                )
            else:
                # 上下文/生成预算真的耗尽到连 128 的最终轮都放不下。
                termination = f"no_answer_after_{exhausted_by}_exhausted"

    if final_answer is not None:
        status = "completed"
    elif termination == "task_timeout":
        status = "timeout"
    else:
        status = "no_answer"

    episode = {
        "run_id": run_id,
        "synthetic": False,
        "task_id": task_id,
        "split": split,
        "condition": condition,
        "status": status,
        "termination_reason": termination,
        "final_answer": final_answer,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "model_calls": model_calls,
        "tool_attempts_executed": observer.executed,
        "tool_attempts_blocked": observer.blocked,
        "config_sha256": cfg.hashes.get("runtime_settings.json"),
    }
    episode_path = writer.close(episode)

    return {
        "episode": episode,
        "episode_path": str(episode_path),
        "turns_path": str(writer.turns_path),
        "messages": messages,
    }


def _record_platform_error(
    *,
    runs_root: str,
    split: str,
    condition: str,
    task_id: str,
    run_id: str,
    exc: BaseException,
    cfg: CourseConfig,
) -> Path:
    """单题平台异常也要落一条 episode，否则 C 汇总时数量对不上且看不出原因。"""
    from ..records.writer import EpisodeWriter

    writer = EpisodeWriter(
        Path(runs_root),
        run_id=run_id,
        slug=safe_slug(f"{task_id}__{run_id}"),
        split=split,
        condition=condition,
        manifest={
            "run_id": run_id,
            "split": split,
            "condition": condition,
            "task_id": task_id,
            "tasks": [task_id],
            "model": cfg.model,
            "upstream_commit": cfg.code_commit,
            "team_commit": _git_head(),
            "course_hashes": cfg.hashes,
            "aborted": True,
        },
    )
    writer.open()
    return writer.close(
        {
            "run_id": run_id,
            "synthetic": False,
            "task_id": task_id,
            "split": split,
            "condition": condition,
            "status": "error",
            "termination_reason": "platform_error",
            "final_answer": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "model_calls": 0,
            "tool_attempts_executed": 0,
            "tool_attempts_blocked": 0,
            "config_sha256": cfg.hashes.get("runtime_settings.json"),
            "error": f"{type(exc).__name__}: {exc}",
        }
    )


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    import os

    from .backend import TransformersBackend
    from .config import load_course_config

    ap = argparse.ArgumentParser(description="跑一个 condition 下的若干 episode")
    ap.add_argument("--task", action="append", help="task_id，可重复；不给则按 --split 取全部")
    ap.add_argument("--split", default="DEV")
    ap.add_argument("--condition", default="A")
    ap.add_argument("--model-dir", default=os.environ.get("MODEL_DIR", os.path.expanduser("~/models/Qwen3.5-4B")))
    ap.add_argument("--runs-root", default="runs/dev_baselines")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 个任务（pilot 用）")
    args = ap.parse_args(argv)

    cfg = load_course_config()
    tasks = args.task or cfg.task_ids(args.split)
    if args.limit:
        tasks = tasks[: args.limit]

    backend = TransformersBackend(
        args.model_dir,
        class_name=cfg.load_class_name(),
        dtype=cfg.model["dtype"],
        eos_token_ids=list(cfg.model["eos_token_ids"]),
        stop_text=cfg.stop_text,
    )

    failures = 0
    for i, task_id in enumerate(tasks, 1):
        print(f"[{i}/{len(tasks)}] {args.condition} :: {task_id}", flush=True)
        run_id = f"{args.split}-{args.condition}-{safe_slug(task_id)}-s{int(cfg.model['seed'])}"
        try:
            result = run_episode(
                task_id=task_id,
                condition=args.condition,
                cfg=cfg,
                backend=backend,
                runs_root=args.runs_root,
                split=args.split,
                run_id=run_id,
            )
        except BaseException as exc:  # noqa: BLE001 - 单题失败不能停掉整批
            failures += 1
            import traceback

            traceback.print_exc()
            path = _record_platform_error(
                runs_root=args.runs_root,
                split=args.split,
                condition=args.condition,
                task_id=task_id,
                run_id=run_id,
                exc=exc,
                cfg=cfg,
            )
            print(f"    !! platform_error -> {path}", flush=True)
            continue

        ep = result["episode"]
        print(
            f"    -> {ep['status']} / {ep['termination_reason']} "
            f"calls={ep['model_calls']} tools={ep['tool_attempts_executed']} "
            f"blocked={ep['tool_attempts_blocked']} answer={ep['final_answer']!r}",
            flush=True,
        )
        print("    " + json.dumps(ep, ensure_ascii=False), flush=True)

    if failures:
        print(f"platform_errors={failures}/{len(tasks)}", flush=True)

    peak = backend.peak_memory_gb()
    if peak is not None:
        print(f"peak_gpu_mem_gb={peak}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
