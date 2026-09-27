"""Build a framework-independent agent execution graph from source span facts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

GRAPH_VERSION = 1
MAX_FEATURE_TOOL_SEQUENCE = 256


class Operation(StrEnum):
    AGENT = "agent"
    MODEL = "model"
    RETRIEVAL = "retrieval"
    MEMORY = "memory"
    TOOL = "tool"
    RETRY = "retry"
    SUBAGENT = "subagent"
    APPROVAL = "approval"
    WORKFLOW = "workflow"
    OTHER = "other"


class Relation(StrEnum):
    CHILD = "child"
    NEXT = "next"
    RETRY_OF = "retry_of"
    DELEGATES_TO = "delegates_to"


@dataclass(frozen=True)
class SpanFact:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    start_ns: int
    end_ns: int
    status: str
    attributes: dict[str, Any] = field(default_factory=dict)
    events: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class GraphNode:
    id: str
    operation: Operation
    label: str
    source_trace_id: str
    source_span_id: str
    start_ns: int
    end_ns: int
    status: str
    details: dict[str, Any]


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    relation: Relation


@dataclass(frozen=True)
class AgentRunGraph:
    run_id: str
    session_id: str
    version: int
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    outcome: str
    terminal_reason: str | None


_EXPLICIT_KINDS = {item.value: item for item in Operation}
_KIND_ALIASES = {
    "sub-agent": Operation.SUBAGENT,
    "sub_agent": Operation.SUBAGENT,
    "human-approval": Operation.APPROVAL,
    "human_approval": Operation.APPROVAL,
    "llm": Operation.MODEL,
    "rag": Operation.RETRIEVAL,
}


def _operation(span: SpanFact) -> Operation:
    attrs = span.attributes
    explicit = str(attrs.get("controlsurface.kind", "")).lower()
    if explicit in _EXPLICIT_KINDS:
        return _EXPLICIT_KINDS[explicit]
    if explicit in _KIND_ALIASES:
        return _KIND_ALIASES[explicit]
    operation = str(attrs.get("gen_ai.operation.name", "")).lower()
    if operation in {"chat", "generate_content", "text_completion", "embeddings"}:
        return Operation.MODEL
    if operation in {"execute_tool", "tool"}:
        return Operation.TOOL
    if operation in {"invoke_agent", "create_agent"}:
        return Operation.AGENT
    if operation in {"retrieve", "retrieval"}:
        return Operation.RETRIEVAL
    if attrs.get("db.operation.name") in {"search", "query"} and attrs.get("db.system.name"):
        return Operation.RETRIEVAL
    return Operation.OTHER


def build_graph(spans: Iterable[SpanFact], run_id: str | None = None) -> AgentRunGraph:
    ordered = sorted(spans, key=lambda span: (span.start_ns, span.trace_id, span.span_id))
    if not ordered:
        raise ValueError("An agent run requires at least one span")
    seen: set[str] = set()
    for span in ordered:
        key = f"{span.trace_id}:{span.span_id}"
        if key in seen:
            raise ValueError(f"Duplicate source span: {key}")
        if span.end_ns < span.start_ns:
            raise ValueError(f"Span ends before it starts: {key}")
        seen.add(key)

    first = ordered[0]
    identity = run_id or str(
        next(
            (
                span.attributes["controlsurface.run.id"]
                for span in ordered
                if span.attributes.get("controlsurface.run.id")
            ),
            first.trace_id,
        )
    )
    session = str(
        next(
            (
                span.attributes["controlsurface.session.id"]
                for span in ordered
                if span.attributes.get("controlsurface.session.id")
            ),
            f"trace:{first.trace_id}",
        )
    )
    nodes = tuple(
        GraphNode(
            id=f"{span.trace_id}:{span.span_id}",
            operation=_operation(span),
            label=span.name,
            source_trace_id=span.trace_id,
            source_span_id=span.span_id,
            start_ns=span.start_ns,
            end_ns=span.end_ns,
            status=span.status,
            details={
                key: span.attributes[key]
                for key in (
                    "gen_ai.operation.name",
                    "gen_ai.request.model",
                    "gen_ai.response.model",
                    "gen_ai.tool.name",
                    "controlsurface.tool.version",
                    "controlsurface.termination_reason",
                )
                if key in span.attributes
            },
        )
        for span in ordered
    )
    by_span = {(node.source_trace_id, node.source_span_id): node.id for node in nodes}
    edges: list[GraphEdge] = []
    siblings: dict[str, list[str]] = {}
    for span, node in zip(ordered, nodes, strict=True):
        parent = by_span.get((span.trace_id, span.parent_span_id or ""))
        if parent:
            edges.append(GraphEdge(parent, node.id, Relation.CHILD))
        siblings.setdefault(parent or "root", []).append(node.id)
        retry_ref = span.attributes.get("controlsurface.retry_of")
        if retry_ref:
            retry_target = by_span.get((span.trace_id, str(retry_ref)))
            if retry_target:
                edges.append(GraphEdge(retry_target, node.id, Relation.RETRY_OF))
        delegate_ref = span.attributes.get("controlsurface.delegates_to")
        if delegate_ref:
            delegate_target = by_span.get((span.trace_id, str(delegate_ref)))
            if delegate_target:
                edges.append(GraphEdge(node.id, delegate_target, Relation.DELEGATES_TO))
    for group in siblings.values():
        edges.extend(
            GraphEdge(left, right, Relation.NEXT)
            for left, right in zip(group, group[1:], strict=False)
        )

    roots = [span for span in ordered if not span.parent_span_id]
    terminal = max(roots or ordered, key=lambda span: span.end_ns)
    reason = terminal.attributes.get("controlsurface.termination_reason")
    # A successful root span must not conceal a failed tool/model child. Agent
    # reliability is an execution-level property, not just the root status.
    outcome = "error" if any(span.status == "error" for span in ordered) else "success"
    if reason in {"cancelled", "timeout", "incomplete"}:
        outcome = str(reason)
    return AgentRunGraph(
        identity,
        session,
        GRAPH_VERSION,
        nodes,
        tuple(edges),
        outcome,
        str(reason) if reason else None,
    )


def graph_features(graph: AgentRunGraph) -> dict[str, Any]:
    tools = [
        str(node.details.get("gen_ai.tool.name") or node.label)
        for node in graph.nodes
        if node.operation is Operation.TOOL
    ]
    retries = sum(edge.relation is Relation.RETRY_OF for edge in graph.edges)
    repeats = sum(left == right for left, right in zip(tools, tools[1:], strict=False))
    return {
        "tool_sequence": tools[:MAX_FEATURE_TOOL_SEQUENCE],
        "tool_count": len(tools),
        "tool_sequence_truncated": len(tools) > MAX_FEATURE_TOOL_SEQUENCE,
        "retry_count": retries,
        "consecutive_tool_repeats": repeats,
        "subagent_count": sum(node.operation is Operation.SUBAGENT for node in graph.nodes),
        "approval_count": sum(node.operation is Operation.APPROVAL for node in graph.nodes),
        "step_count": len(graph.nodes),
        "outcome": graph.outcome,
        "termination_reason": graph.terminal_reason,
    }
