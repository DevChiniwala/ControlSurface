"""Deterministic release policy and content-hashed decision evidence."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

from .changes import canonical_json


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    passed: bool
    quality_score: float
    tool_correct: bool
    latency_ms: int
    cost_nano_usd: int

    def __post_init__(self) -> None:
        if not self.case_id:
            raise ValueError("Case ID must not be empty")
        if not math.isfinite(self.quality_score) or not 0 <= self.quality_score <= 1:
            raise ValueError("Quality score must be finite and between zero and one")
        if self.latency_ms < 0 or self.cost_nano_usd < 0:
            raise ValueError("Latency and cost must not be negative")


@dataclass(frozen=True)
class GatePolicy:
    revision: str
    minimum_cases: int = 1
    maximum_regressions: int = 0
    minimum_tool_accuracy_delta: float = -0.01
    minimum_quality_delta: float | None = None
    maximum_latency_delta_ms: float | None = None
    maximum_cost_delta_nano_usd: float | None = None
    critical_case_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.revision or self.minimum_cases < 1 or self.maximum_regressions < 0:
            raise ValueError("Gate policy requires a revision and valid case limits")
        if not math.isfinite(self.minimum_tool_accuracy_delta):
            raise ValueError("Tool accuracy threshold must be finite")
        for threshold in (
            self.minimum_quality_delta,
            self.maximum_latency_delta_ms,
            self.maximum_cost_delta_nano_usd,
        ):
            if threshold is not None and not math.isfinite(threshold):
                raise ValueError("Gate thresholds must be finite")
        if len(set(self.critical_case_ids)) != len(self.critical_case_ids):
            raise ValueError("Critical case IDs must be unique")


@dataclass(frozen=True)
class GateDecision:
    passed: bool
    regressions: tuple[str, ...]
    reasons: tuple[str, ...]
    baseline_tool_accuracy: float
    candidate_tool_accuracy: float
    quality_delta: float
    latency_delta_ms: float
    cost_delta_nano_usd: float


def decide_gate(
    baseline: Iterable[CaseResult], candidate: Iterable[CaseResult], policy: GatePolicy
) -> GateDecision:
    baseline_items = tuple(baseline)
    candidate_items = tuple(candidate)
    before = {result.case_id: result for result in baseline_items}
    after = {result.case_id: result for result in candidate_items}
    if len(before) != len(baseline_items) or len(after) != len(candidate_items):
        raise ValueError("Duplicate case IDs are not valid release evidence")
    if set(before) != set(after):
        raise ValueError("Baseline and candidate must contain the same case IDs")
    if len(before) < policy.minimum_cases:
        raise ValueError("Insufficient paired cases for gate policy")
    ids = sorted(before)
    regressions = tuple(
        case_id for case_id in ids if before[case_id].passed and not after[case_id].passed
    )
    baseline_tool = sum(before[i].tool_correct for i in ids) / len(ids)
    candidate_tool = sum(after[i].tool_correct for i in ids) / len(ids)
    quality_delta = sum(after[i].quality_score - before[i].quality_score for i in ids) / len(ids)
    latency_delta = sum(after[i].latency_ms - before[i].latency_ms for i in ids) / len(ids)
    cost_delta = sum(after[i].cost_nano_usd - before[i].cost_nano_usd for i in ids) / len(ids)
    reasons: list[str] = []
    if len(regressions) > policy.maximum_regressions:
        reasons.append("regression_limit")
    if candidate_tool - baseline_tool < policy.minimum_tool_accuracy_delta:
        reasons.append("tool_accuracy")
    if set(regressions) & set(policy.critical_case_ids):
        reasons.append("critical_regression")
    if policy.minimum_quality_delta is not None and quality_delta < policy.minimum_quality_delta:
        reasons.append("quality")
    if (
        policy.maximum_latency_delta_ms is not None
        and latency_delta > policy.maximum_latency_delta_ms
    ):
        reasons.append("latency")
    if (
        policy.maximum_cost_delta_nano_usd is not None
        and cost_delta > policy.maximum_cost_delta_nano_usd
    ):
        reasons.append("cost")
    return GateDecision(
        not reasons,
        regressions,
        tuple(reasons),
        baseline_tool,
        candidate_tool,
        quality_delta,
        latency_delta,
        cost_delta,
    )


def release_evidence(
    baseline: Iterable[CaseResult],
    candidate: Iterable[CaseResult],
    policy: GatePolicy,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    before = tuple(sorted(baseline, key=lambda item: item.case_id))
    after = tuple(sorted(candidate, key=lambda item: item.case_id))
    required = {
        "baseline_version",
        "candidate_version",
        "dataset_revision",
        "suite_revision",
        "evaluator_versions",
        "prompt_hashes",
        "tool_schema_hashes",
        "model_configuration",
        "pricing_version",
        "execution_environment",
        "sampling_parameters",
    }
    missing = required - manifest.keys()
    if missing:
        raise ValueError(f"Incomplete evidence manifest: {', '.join(sorted(missing))}")
    decision = decide_gate(before, after, policy)
    payload: dict[str, Any] = {
        "format_version": 1,
        "manifest": manifest,
        "policy": asdict(policy),
        "baseline_results": [asdict(item) for item in before],
        "candidate_results": [asdict(item) for item in after],
        "decision": asdict(decision),
    }
    payload["sha256"] = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return payload


def verify_evidence(bundle: dict[str, Any]) -> bool:
    try:
        received = bundle.get("sha256")
        if not isinstance(received, str):
            return False
        content = {key: value for key, value in bundle.items() if key != "sha256"}
        if hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest() != received:
            return False
        policy = GatePolicy(**content["policy"])
        baseline = [CaseResult(**item) for item in content["baseline_results"]]
        candidate = [CaseResult(**item) for item in content["candidate_results"]]
        recomputed = asdict(decide_gate(baseline, candidate, policy))
        return canonical_json(recomputed) == canonical_json(content["decision"])
    except (KeyError, TypeError, ValueError):
        return False
