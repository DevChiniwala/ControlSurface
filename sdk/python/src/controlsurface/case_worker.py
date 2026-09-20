"""Execute one explicitly user-supplied local candidate/evaluator in a child process."""

from __future__ import annotations

import contextlib
import importlib
import json
import sys
from collections.abc import Callable
from typing import Any


def _load(target: str) -> Callable[..., Any]:
    if ":" not in target:
        raise ValueError("Callable must be module:function")
    module, name = target.split(":", 1)
    value = getattr(importlib.import_module(module), name)
    if not callable(value):
        raise ValueError("Target is not callable")
    return value


def main() -> None:
    request = json.load(sys.stdin)
    with contextlib.redirect_stdout(sys.stderr):
        candidate = _load(request["candidate"])
        actual = candidate(request["input"])
        if not isinstance(actual, dict):
            raise ValueError("Candidate must return a JSON object")
        custom = None
        if request.get("evaluator"):
            evaluator = _load(request["evaluator"])
            custom = evaluator(request["input"], request["expected"], actual)
    print(json.dumps({"actual": actual, "custom": custom}, separators=(",", ":")))


if __name__ == "__main__":
    main()
