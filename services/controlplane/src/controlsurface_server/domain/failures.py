"""Deterministic failure grouping and representative case selection."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass

from .changes import canonical_json
from .graph import AgentRunGraph, graph_features


@dataclass(frozen=True)
class FailedRun:
    graph: AgentRunGraph
    error_type: str
    failed_tool: str | None
    input_fingerprint: str
    occurred_ns: int


@dataclass(frozen=True)
class FailureCluster:
    signature: str
    run_ids: tuple[str, ...]
    representative_run_ids: tuple[str, ...]
    features: dict[str, object]


def failure_signature(run: FailedRun) -> tuple[str, dict[str, object]]:
    features = graph_features(run.graph)
    structural = {
        "tool_sequence": features["tool_sequence"][:64],
        "tool_count_bucket": min(int(features["tool_count"]), 64),
        "retry_count": min(int(features["retry_count"]), 3),
        "consecutive_tool_repeats": min(int(features["consecutive_tool_repeats"]), 3),
        "subagent_count": min(int(features["subagent_count"]), 3),
        "termination_reason": features["termination_reason"],
        "outcome": features["outcome"],
        "error_type": run.error_type.strip().lower(),
        "failed_tool": (run.failed_tool or "").strip().lower(),
    }
    digest = hashlib.sha256(canonical_json(structural).encode()).hexdigest()[:24]
    return digest, structural


def cluster_failures(runs: Iterable[FailedRun]) -> tuple[FailureCluster, ...]:
    groups: dict[str, list[FailedRun]] = {}
    descriptions: dict[str, dict[str, object]] = {}
    for run in runs:
        signature, features = failure_signature(run)
        groups.setdefault(signature, []).append(run)
        descriptions[signature] = features

    clusters: list[FailureCluster] = []
    for signature, members in groups.items():
        ordered = sorted(members, key=lambda item: (item.occurred_ns, item.graph.run_id))
        counts: dict[str, int] = {}
        for member in ordered:
            counts[member.input_fingerprint] = counts.get(member.input_fingerprint, 0) + 1
        representatives: list[str] = []
        for fingerprint in sorted(counts, key=lambda key: (-counts[key], key)):
            matching = [member for member in ordered if member.input_fingerprint == fingerprint]
            representatives.append(matching[len(matching) // 2].graph.run_id)
            if len(representatives) == 3:
                break
        clusters.append(
            FailureCluster(
                signature,
                tuple(member.graph.run_id for member in ordered),
                tuple(representatives),
                descriptions[signature],
            )
        )
    return tuple(sorted(clusters, key=lambda item: (-len(item.run_ids), item.signature)))
