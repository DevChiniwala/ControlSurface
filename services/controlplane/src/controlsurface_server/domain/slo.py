"""Agent reliability measurements with explicit sample and no-data rules."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class Health(StrEnum):
    NO_DATA = "no_data"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    SLO_BURN = "slo_burn"
    INCIDENT = "incident"


@dataclass(frozen=True)
class RunMeasurement:
    run_id: str
    complete: bool
    tool_calls: int
    successful_tool_calls: int
    latency_ms: int
    cost_nano_usd: int
    steps: int


@dataclass(frozen=True)
class SloPolicy:
    minimum_samples: int = 20
    completion_rate_min: float = 0.98
    tool_success_rate_min: float = 0.99
    p95_latency_ms_max: int = 8000
    average_cost_nano_usd_max: int = 80_000_000
    maximum_steps_max: int = 12

    def __post_init__(self) -> None:
        if self.minimum_samples < 1:
            raise ValueError("minimum_samples must be positive")
        for name in ("completion_rate_min", "tool_success_rate_min"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between zero and one")
        for name in (
            "p95_latency_ms_max",
            "average_cost_nano_usd_max",
            "maximum_steps_max",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must not be negative")


@dataclass(frozen=True)
class SloMetrics:
    samples: int
    completed_runs: int
    tool_calls: int
    successful_tool_calls: int
    p95_latency_ms: int
    total_cost_nano_usd: int
    maximum_steps: int


@dataclass(frozen=True)
class SloResult:
    health: Health
    samples: int
    completion_rate: float | None
    tool_success_rate: float | None
    p95_latency_ms: int | None
    average_cost_nano_usd: int | None
    maximum_steps: int | None
    breaches: tuple[str, ...]


def _p95(values: list[int]) -> int:
    ordered = sorted(values)
    index = max(0, (95 * len(ordered) + 99) // 100 - 1)
    return ordered[index]


def evaluate_slo_metrics(
    metrics: SloMetrics,
    policy: SloPolicy,
    consecutive_breached_windows: int = 0,
    incident_open: bool = False,
) -> SloResult:
    if metrics.samples < policy.minimum_samples:
        health = Health.INCIDENT if incident_open else Health.NO_DATA
        return SloResult(health, metrics.samples, None, None, None, None, None, ())
    tool_success = (
        metrics.successful_tool_calls / metrics.tool_calls if metrics.tool_calls else None
    )
    completion = metrics.completed_runs / metrics.samples
    latency = metrics.p95_latency_ms
    cost = round(metrics.total_cost_nano_usd / metrics.samples)
    steps = metrics.maximum_steps
    breaches: list[str] = []
    if completion < policy.completion_rate_min:
        breaches.append("completion_rate")
    if tool_success is not None and tool_success < policy.tool_success_rate_min:
        breaches.append("tool_success_rate")
    if latency > policy.p95_latency_ms_max:
        breaches.append("p95_latency_ms")
    if cost > policy.average_cost_nano_usd_max:
        breaches.append("average_cost_nano_usd")
    if steps > policy.maximum_steps_max:
        breaches.append("maximum_steps")
    health = (
        Health.INCIDENT
        if incident_open
        else Health.SLO_BURN
        if breaches and consecutive_breached_windows >= 3
        else Health.DEGRADED
        if breaches
        else Health.HEALTHY
    )
    return SloResult(
        health, metrics.samples, completion, tool_success, latency, cost, steps, tuple(breaches)
    )


def evaluate_slo(
    runs: Iterable[RunMeasurement],
    policy: SloPolicy,
    consecutive_breached_windows: int = 0,
    incident_open: bool = False,
) -> SloResult:
    items = list(runs)
    metrics = SloMetrics(
        samples=len(items),
        completed_runs=sum(item.complete for item in items),
        tool_calls=sum(item.tool_calls for item in items),
        successful_tool_calls=sum(item.successful_tool_calls for item in items),
        p95_latency_ms=_p95([item.latency_ms for item in items]) if items else 0,
        total_cost_nano_usd=sum(item.cost_nano_usd for item in items),
        maximum_steps=max((item.steps for item in items), default=0),
    )
    return evaluate_slo_metrics(metrics, policy, consecutive_breached_windows, incident_open)
