"""Offline answer scoring for CodeAct episodes.

Pure standard library, Python 3.10 compatible.  No network, no model, no
float conversion for numeric comparison.  The reference answer and its type
are supplied by the *offline* reference file owned by C; they are never
inferred from the prediction and never enter a runtime/feedback context.
"""

from __future__ import annotations

from decimal import (
    Decimal,
    InvalidOperation,
    MAX_EMAX,
    MIN_EMIN,
    localcontext,
)
from typing import Any

from .errors import DataError

NUMERIC_TOLERANCE = Decimal("0.000001")  # 1e-6, exact Decimal (never float)
SUPPORTED_ANSWER_TYPES = ("numeric", "string")

REASON_CORRECT = "correct"
REASON_NUMERIC_MISMATCH = "numeric_mismatch"
REASON_STRING_MISMATCH = "string_mismatch"
REASON_NO_ANSWER = "no_answer"
REASON_UNPARSEABLE_PREDICTION = "unparseable_prediction"
REASON_NONFINITE_PREDICTION = "nonfinite_prediction"


def _coerce_decimal(value: Any) -> Decimal | None:
    """Return an exact Decimal, or None when the value is not a finite number.

    bool is rejected explicitly even though it subclasses int in Python.
    Callers decide whether None means a data error (reference) or a recorded
    model failure (prediction).
    """
    try:
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, Decimal):
            dec = value
        elif isinstance(value, int):
            dec = Decimal(value)
        elif isinstance(value, float):
            # JSON floats are unavoidable on input, but we convert via str(),
            # never by doing arithmetic/comparison in binary floating point.
            dec = Decimal(str(value))
        elif isinstance(value, str):
            dec = Decimal(value.strip())
        else:
            return None
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        return None

    if not dec.is_finite():
        return None
    return dec


def _decimal_within_tolerance(pred: Decimal, ref: Decimal) -> bool:
    """Compare |pred-ref| <= 1e-6 with dynamically raised Decimal precision.

    The context precision is sized from the operands' own exponents so that
    high-precision and very large values are not rounded into a wrong verdict
    by Decimal's default 28-digit context.
    """
    tp, tr = pred.as_tuple(), ref.as_tuple()
    exponent_min = min(tp.exponent, tr.exponent)
    adjusted_max = max(pred.adjusted(), ref.adjusted())
    digits_max = max(len(tp.digits), len(tr.digits))
    precision = max(50, adjusted_max - exponent_min + digits_max + 8)

    with localcontext() as ctx:
        ctx.prec = precision
        ctx.Emax = MAX_EMAX
        ctx.Emin = MIN_EMIN
        difference = abs(pred - ref)
        return difference <= NUMERIC_TOLERANCE


def score_episode(episode: dict, *, reference: Any, answer_type: str) -> dict:
    """Score one episode and return a *new* dict with ``success``/``scoring_reason``.

    The input episode is never mutated and the reference is never copied into
    the output.  A null/missing final answer is a recorded failure, not an
    error and not a dropped sample.
    """
    if not isinstance(episode, dict):
        raise DataError(f"episode must be a dict, got {type(episode).__name__}")
    if answer_type not in SUPPORTED_ANSWER_TYPES:
        raise DataError(
            f"unknown answer_type {answer_type!r}; expected one of {SUPPORTED_ANSWER_TYPES}"
        )

    prediction = episode.get("final_answer")
    result = dict(episode)  # preserve all online fields, no mutation

    # Validate the declared reference type BEFORE the null-answer shortcut.
    # A missing answer must never hide a corrupt/invalid offline reference: that
    # would turn a data error into a silent "model was wrong".
    if answer_type == "numeric":
        ref_dec = _coerce_decimal(reference)
        if ref_dec is None:
            raise DataError(
                f"reference for task {episode.get('task_id')!r} is not a finite numeric "
                f"value: {reference!r}"
            )
    else:  # answer_type == "string"
        if not isinstance(reference, str):
            raise DataError(
                f"reference for task {episode.get('task_id')!r} must be a string for "
                f"answer_type='string', got {type(reference).__name__}"
            )

    if prediction is None:
        result["success"] = False
        result["scoring_reason"] = REASON_NO_ANSWER
        result["answer_type"] = answer_type
        return result

    if answer_type == "numeric":
        pred_dec = _coerce_decimal(prediction)
        if pred_dec is None:
            # A NaN/Infinity/unparseable *prediction* is a model failure we keep;
            # the same problem in a *reference* is a data error above.
            raw = str(prediction).strip()
            if raw.lower() in {"nan", "+nan", "-nan", "inf", "+inf", "-inf",
                               "infinity", "+infinity", "-infinity"}:
                reason = REASON_NONFINITE_PREDICTION
            else:
                reason = REASON_UNPARSEABLE_PREDICTION
            success = False
        else:
            success = _decimal_within_tolerance(pred_dec, ref_dec)
            reason = REASON_CORRECT if success else REASON_NUMERIC_MISMATCH
    else:  # answer_type == "string"; reference already validated above
        if not isinstance(prediction, str):
            # Non-string predictions simply cannot match; keep as a failure.
            success, reason = False, REASON_STRING_MISMATCH
        else:
            success = prediction.strip() == reference.strip()
            reason = REASON_CORRECT if success else REASON_STRING_MISMATCH

    result["success"] = success
    result["scoring_reason"] = reason
    result["answer_type"] = answer_type
    return result
