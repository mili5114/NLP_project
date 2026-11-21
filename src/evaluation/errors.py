"""Shared exceptions for C's offline evaluation tools.

All exceptions raised for bad *data* (as opposed to a genuine model failure)
derive from EvaluationError, so CLI entry points can return a non-zero exit
code and never silently treat a data problem as "the model answered wrong".
"""


class EvaluationError(Exception):
    """Base class for every recoverable error in the offline toolchain."""


class DataError(EvaluationError):
    """Offline reference data or episode structure is invalid / inconsistent."""


class InputError(EvaluationError):
    """Input files, paths or CLI-provided expectation sets are invalid."""


class SyntheticNotAllowed(InputError):
    """Synthetic records were supplied without --allow-synthetic."""
