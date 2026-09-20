import json
from copy import deepcopy

import pytest

from controlsurface_server.domain.changes import Compatibility, compare_contracts, fingerprint
from controlsurface_server.domain.failures import FailedRun, cluster_failures
from controlsurface_server.domain.graph import (
    Operation,
    Relation,
    SpanFact,
    build_graph,
    graph_features,
)
from controlsurface_server.domain.release import (
    CaseResult,
    GatePolicy,
    decide_gate,
    release_evidence,
    verify_evidence,
)
from controlsurface_server.domain.slo import Health, RunMeasurement, SloPolicy, evaluate_slo


def _span(span_id: str, parent: str | None, kind: str, start: int, **attrs: object) -> SpanFact:
    return SpanFact(
        trace_id="a" * 32,
        span_id=span_id,
        parent_span_id=parent,
        name=kind,
        start_ns=start,
        end_ns=start + 10,
        status="ok",
        attributes={"controlsurface.kind": kind, **attrs},
    )


def test_run_graph_links_retry_and_preserves_source_references() -> None:
    root = _span("1" * 16, None, "agent", 1, **{"controlsurface.run.id": "run-1"})
    failed_tool = _span("2" * 16, root.span_id, "tool", 2, **{"gen_ai.tool.name": "refund"})
    retry = _span(
        "3" * 16,
        root.span_id,
        "retry",
        3,
        **{"controlsurface.retry_of": failed_tool.span_id},
    )
    graph = build_graph([retry, root, failed_tool])
    assert graph.run_id == "run-1"
    assert [node.operation for node in graph.nodes] == [
        Operation.AGENT,
        Operation.TOOL,
        Operation.RETRY,
    ]
    assert any(edge.relation is Relation.RETRY_OF for edge in graph.edges)
    assert graph.nodes[1].source_span_id == failed_tool.span_id
    assert graph_features(graph)["retry_count"] == 1


def test_duplicate_source_span_is_rejected() -> None:
    span = _span("1" * 16, None, "agent", 1)
    with pytest.raises(ValueError, match="Duplicate source span"):
        build_graph([span, span])


def test_schema_change_identifies_breaking_required_shape() -> None:
    before = {
        "type": "object",
        "properties": {"amount": {"type": "number"}},
        "required": ["amount"],
    }
    after = {
        "type": "object",
        "properties": {"amount": {"type": "object"}, "currency": {"type": "string"}},
        "required": ["amount", "currency"],
    }
    result = compare_contracts(before, after)
    assert result.compatibility is Compatibility.BREAKING
    assert {change.path for change in result.changes} == {"amount", "currency"}
    assert result.before_fingerprint != result.after_fingerprint
    assert fingerprint(
        {"required": ["amount"], "properties": before["properties"], "type": "object"}
    ) == fingerprint(before)


def test_failure_cluster_selects_distinct_inputs() -> None:
    runs = []
    for index, input_key in enumerate(
        ["duplicate", "duplicate", "duplicate", "missing", "special"]
    ):
        graph = build_graph(
            [_span(f"{index + 1:016x}", None, "agent", index + 1)], run_id=f"run-{index}"
        )
        runs.append(FailedRun(graph, "ToolSchemaError", "refund", input_key, index))
    clusters = cluster_failures(runs)
    assert len(clusters) == 1
    assert len(clusters[0].run_ids) == 5
    assert len(clusters[0].representative_run_ids) == 3


def test_slo_no_data_then_tool_degradation() -> None:
    runs = [RunMeasurement(str(i), True, 1, 1, 100, 1_000_000, 4) for i in range(19)]
    policy = SloPolicy()
    assert evaluate_slo(runs, policy).health is Health.NO_DATA
    runs.append(RunMeasurement("bad", False, 1, 0, 200, 1_000_000, 5))
    assert evaluate_slo(runs, policy).health is Health.DEGRADED
    assert evaluate_slo(runs, policy, consecutive_breached_windows=3).health is Health.SLO_BURN


def test_release_evidence_is_recomputable_and_tamper_evident() -> None:
    baseline = [CaseResult("refund", True, 0.9, True, 100, 1000)]
    candidate = [CaseResult("refund", False, 0.7, False, 90, 900)]
    manifest = {
        "baseline_version": "prod-a",
        "candidate_version": "fix-b",
        "dataset_revision": "data-1",
        "suite_revision": "suite-1",
        "evaluator_versions": {"task": "2"},
        "prompt_hashes": ["prompt-hash"],
        "tool_schema_hashes": ["schema-hash"],
        "model_configuration": {"model": "fixture"},
        "pricing_version": "price-1",
        "execution_environment": {"python": "3.13"},
        "sampling_parameters": {"seed": 42},
    }
    bundle = release_evidence(baseline, candidate, GatePolicy("gate-1"), manifest)
    assert bundle["decision"]["passed"] is False
    assert verify_evidence(bundle)
    assert verify_evidence(json.loads(json.dumps(bundle)))
    tampered = deepcopy(bundle)
    tampered["candidate_results"][0]["passed"] = True
    assert not verify_evidence(tampered)


def test_release_gate_rejects_duplicate_case_ids() -> None:
    case = CaseResult("same", True, 1.0, True, 100, 100)
    with pytest.raises(ValueError, match="Duplicate case IDs"):
        decide_gate([case, case], [case, case], GatePolicy("v1"))


def test_release_gate_enforces_quality_latency_and_cost_bounds() -> None:
    baseline = [CaseResult("case", True, 0.9, True, 100, 100)]
    candidate = [CaseResult("case", True, 0.4, True, 300, 300)]
    policy = GatePolicy(
        "v1",
        minimum_quality_delta=0,
        maximum_latency_delta_ms=0,
        maximum_cost_delta_nano_usd=0,
    )
    decision = decide_gate(baseline, candidate, policy)
    assert decision.passed is False
    assert decision.reasons == ("quality", "latency", "cost")
