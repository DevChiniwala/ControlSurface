"""Failure intelligence, incidents, and production-derived regression APIs."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from datetime import UTC, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from .dependencies import advisory_lock_key
from .dependencies import authorized_project as _authorized_project
from .dependencies import query_clickhouse as _query
from .domain.changes import canonical_json
from .domain.release import CaseResult, GatePolicy, release_evidence
from .settings import Settings, load_settings
from .storage import postgres

router = APIRouter(prefix="/api/projects/{project_id}")


def _trace_detail(
    project_id: uuid.UUID, trace_id: str, authorized: str, settings: Settings
) -> dict[str, Any]:
    # Lazy import keeps route modules independently importable while reusing the
    # same trace reader. API imports this router only after defining the reader.
    from .api import trace_detail

    return trace_detail(project_id, trace_id, authorized, settings)


class AnalyzeInput(BaseModel):
    cluster_signature: str = Field(pattern=r"^[a-f0-9]{24}$")
    severity: str = Field(default="medium", pattern=r"^(low|medium|high|critical)$")


class RegressionInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_trace_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    cluster_signature: str | None = None
    input: dict[str, Any]
    expect: dict[str, Any]


class DatasetInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class DatasetItemInput(BaseModel):
    input: dict[str, Any]
    expected: dict[str, Any]


class ReleaseInput(BaseModel):
    baseline: list[CaseResult] = Field(max_length=5000)
    candidate: list[CaseResult] = Field(max_length=5000)
    policy: GatePolicy
    manifest: dict[str, Any]


def _failure_rows(settings: Settings, project_id: str) -> list[dict[str, Any]]:
    return _query(
        settings,
        "SELECT trace_id, run_id, features_json, graph_json, updated_at, occurred_at "
        "FROM agent_run_graphs FINAL WHERE project_id = {project_id:UUID} "
        "AND outcome != 'success' ORDER BY updated_at DESC LIMIT 2000",
        {"project_id": project_id},
    )


def _clusters(settings: Settings, project_id: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _failure_rows(settings, project_id):
        if isinstance(row["trace_id"], bytes):
            row["trace_id"] = row["trace_id"].decode("ascii").rstrip("\x00")
        features = json.loads(row["features_json"])
        signature = features.get("failure_signature")
        if signature:
            grouped[signature].append({**row, "features": features})
    clusters = []
    for signature, rows in grouped.items():
        fingerprints: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            fingerprints[row["features"].get("input_fingerprint", row["trace_id"])].append(row)
        representatives = [
            sorted(members, key=lambda item: item["updated_at"])[len(members) // 2]
            for _, members in sorted(fingerprints.items(), key=lambda pair: -len(pair[1]))[:3]
        ]
        clusters.append(
            {
                "signature": signature,
                "count": len(rows),
                "first_seen": min(row["occurred_at"] for row in rows),
                "last_seen": max(row["occurred_at"] for row in rows),
                "features": rows[0]["features"].get("failure_structure", {}),
                "representatives": [
                    {"trace_id": row["trace_id"], "run_id": row["run_id"]}
                    for row in representatives
                ],
            }
        )
    return sorted(clusters, key=lambda item: (-item["count"], item["signature"]))


@router.get("/clusters")
def list_clusters(
    project_id: uuid.UUID,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(load_settings),
) -> list[dict[str, Any]]:
    return jsonable_encoder(_clusters(settings, str(project_id)))


@router.post("/incidents/analyze", status_code=201)
def analyze_incident(
    project_id: uuid.UUID,
    data: AnalyzeInput,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(load_settings),
) -> dict[str, Any]:
    cluster = next(
        (
            item
            for item in _clusters(settings, str(project_id))
            if item["signature"] == data.cluster_signature
        ),
        None,
    )
    if not cluster:
        raise HTTPException(404, "Failure cluster not found")
    failed_tool = str(cluster["features"].get("failed_tool") or "")
    representative = cluster["representatives"][0]["trace_id"]
    detail = _trace_detail(project_id, representative, str(project_id), settings)
    agent_name = next(
        (
            str(span["attributes"]["controlsurface.agent.name"])
            for span in detail["spans"]
            if span["attributes"].get("controlsurface.agent.name")
        ),
        "",
    )
    first_seen = cluster["first_seen"]
    if first_seen.tzinfo is None:
        first_seen = first_seen.replace(tzinfo=UTC)
    last_seen = cluster["last_seen"]
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=UTC)
    with postgres(settings) as connection:
        connection.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            (advisory_lock_key("incident-cluster", project_id, data.cluster_signature),),
        )
        previous = connection.execute(
            "SELECT id, agent_name FROM incidents WHERE project_id = %s AND cluster_signature = %s "
            "AND status = 'open' ORDER BY created_at DESC LIMIT 1",
            (project_id, data.cluster_signature),
        ).fetchone()
        if previous:
            if agent_name and not previous["agent_name"]:
                connection.execute(
                    "UPDATE incidents SET agent_name = %s WHERE id = %s",
                    (agent_name, previous["id"]),
                )
            return {"id": str(previous["id"]), "existing": True}
        changes = connection.execute(
            "SELECT id, change_type, subject_type, subject_name, before_version, "
            "after_version, before_hash, after_hash, effective_at, deployment_id "
            "FROM change_events WHERE project_id = %s AND effective_at >= %s "
            "AND effective_at <= %s ORDER BY effective_at DESC LIMIT 100",
            (project_id, first_seen - timedelta(hours=2), first_seen),
        ).fetchall()
        candidates = []
        for change in changes:
            minutes = max(0, (first_seen - change["effective_at"]).total_seconds() / 60)
            match = bool(failed_tool and change["subject_name"].lower() == failed_tool.lower())
            score = round((0.55 if match else 0.1) + 0.35 * max(0, 1 - minutes / 120), 3)
            candidates.append(
                {
                    "change_id": str(change["id"]),
                    "subject": change["subject_name"],
                    "change_type": change["change_type"],
                    "before_version": change["before_version"],
                    "after_version": change["after_version"],
                    "before_hash": change["before_hash"],
                    "after_hash": change["after_hash"],
                    "effective_at": change["effective_at"].isoformat(),
                    "minutes_before_first_failure": round(minutes, 2),
                    "failed_tool_matches": match,
                    "evidence_score": score,
                    "explanation": "Temporal association and tool identity; not causal proof",
                }
            )
        candidates.sort(key=lambda item: -item["evidence_score"])
        evidence = {
            "cluster": {
                key: value
                for key, value in cluster.items()
                if key != "first_seen" and key != "last_seen"
            },
            "root_cause_candidates": candidates[:10],
            "method": "time_window_v1",
            "limitations": "Scores rank inspectable associations; no counterfactual causal test.",
        }
        incident_id = uuid.uuid4()
        title = f"{failed_tool or 'Agent run'} failure cluster {data.cluster_signature[:8]}"
        connection.execute(
            "INSERT INTO incidents(id, project_id, agent_name, title, severity, "
            "cluster_signature, first_seen, last_seen, affected_runs, evidence_json) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                incident_id,
                project_id,
                agent_name,
                title,
                data.severity,
                data.cluster_signature,
                first_seen,
                last_seen,
                cluster["count"],
                json.dumps(evidence, default=str),
            ),
        )
    return {"id": str(incident_id), "existing": False, "evidence": evidence}


@router.get("/incidents")
def list_incidents(
    project_id: uuid.UUID,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(load_settings),
) -> list[dict[str, Any]]:
    with postgres(settings) as connection:
        rows = connection.execute(
            "SELECT id, title, severity, status, cluster_signature, first_seen, last_seen, "
            "affected_runs, created_at FROM incidents WHERE project_id = %s "
            "ORDER BY created_at DESC LIMIT 100",
            (project_id,),
        ).fetchall()
    return jsonable_encoder(rows)


@router.get("/incidents/{incident_id}")
def incident_detail(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(load_settings),
) -> dict[str, Any]:
    with postgres(settings) as connection:
        row = connection.execute(
            "SELECT * FROM incidents WHERE id = %s AND project_id = %s",
            (incident_id, project_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Incident not found")
    return jsonable_encoder(row)


@router.get("/regressions/candidates")
def regression_candidates(
    project_id: uuid.UUID,
    cluster_signature: str = Query(pattern=r"^[a-f0-9]{24}$"),
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(load_settings),
) -> list[dict[str, Any]]:
    cluster = next(
        (
            item
            for item in _clusters(settings, str(project_id))
            if item["signature"] == cluster_signature
        ),
        None,
    )
    if not cluster:
        raise HTTPException(404, "Failure cluster not found")
    candidates = []
    for representative in cluster["representatives"]:
        trace_id = representative["trace_id"]
        detail = _trace_detail(project_id, trace_id, str(project_id), settings)
        source = next(
            (span for span in detail["spans"] if "controlsurface.input" in span["attributes"]),
            None,
        )
        raw_input = source["attributes"]["controlsurface.input"] if source else None
        if isinstance(raw_input, str):
            try:
                parsed = json.loads(raw_input)
            except json.JSONDecodeError:
                parsed = raw_input
        else:
            parsed = raw_input
        proposed_input = (
            parsed
            if isinstance(parsed, dict)
            else {"message": parsed}
            if parsed is not None
            else {}
        )
        candidates.append(
            {
                "name": f"Production failure {trace_id[:8]}",
                "source_trace_id": trace_id,
                "cluster_signature": cluster_signature,
                "input": proposed_input,
                "expect": {"completion": True},
                "review_required": True,
                "evidence": {
                    "affected_runs": cluster["count"],
                    "failure_structure": cluster["features"],
                    "input_available": raw_input is not None,
                    "observed_outcome": detail["graph"]["outcome"],
                },
            }
        )
    return candidates


@router.post("/regressions", status_code=201)
def create_regression(
    project_id: uuid.UUID,
    data: RegressionInput,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(load_settings),
) -> dict[str, str]:
    detail = _trace_detail(project_id, data.source_trace_id, str(project_id), settings)
    if (
        data.cluster_signature
        and (detail["features"] or {}).get("failure_signature") != data.cluster_signature
    ):
        raise HTTPException(422, "Trace does not belong to this failure cluster")
    spans = detail["spans"]
    source_context = {
        "graph_version": (detail["graph"] or {}).get("version"),
        "agent_versions": sorted(
            {span["agent_version"] for span in spans if span["agent_version"]}
        ),
        "models": sorted({span["model_name"] for span in spans if span["model_name"]}),
        "tool_versions": [
            {"name": name, "schema_version": version}
            for name, version in sorted(
                {
                    (
                        span["tool_name"],
                        str(span["attributes"].get("controlsurface.tool.schema_version") or ""),
                    )
                    for span in spans
                    if span["tool_name"]
                }
            )
        ],
    }
    case = {
        "name": data.name,
        "source_trace_id": data.source_trace_id,
        "cluster_signature": data.cluster_signature,
        "input": data.input,
        "expect": data.expect,
        "source_context": source_context,
        "format_version": 1,
    }
    revision = hashlib.sha256(canonical_json(case).encode()).hexdigest()
    case_id = uuid.uuid4()
    with postgres(settings) as connection:
        lock_keys = {advisory_lock_key("regression-source", project_id, data.source_trace_id)}
        if data.cluster_signature:
            lock_keys.add(
                advisory_lock_key(
                    "regression-equivalent",
                    project_id,
                    data.cluster_signature,
                    canonical_json(data.input),
                )
            )
        for lock_key in sorted(lock_keys):
            connection.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
        existing = connection.execute(
            "SELECT id, revision FROM regression_cases WHERE project_id = %s "
            "AND source_trace_id = %s",
            (project_id, data.source_trace_id),
        ).fetchone()
        if existing:
            raise HTTPException(409, "This trace already has a regression case")
        if data.cluster_signature:
            equivalent = connection.execute(
                "SELECT id FROM regression_cases WHERE project_id = %s "
                "AND cluster_signature = %s AND case_json->'input' = %s::jsonb LIMIT 1",
                (project_id, data.cluster_signature, json.dumps(data.input)),
            ).fetchone()
            if equivalent:
                raise HTTPException(
                    409, "An equivalent input already exists in this failure cluster"
                )
        connection.execute(
            "INSERT INTO regression_cases(id, project_id, name, source_trace_id, "
            "cluster_signature, revision, case_json) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                case_id,
                project_id,
                data.name,
                data.source_trace_id,
                data.cluster_signature,
                revision,
                json.dumps(case),
            ),
        )
    return {"id": str(case_id), "revision": revision}


@router.get("/regressions/suite")
def export_regression_suite(
    project_id: uuid.UUID,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(load_settings),
) -> dict[str, Any]:
    with postgres(settings) as connection:
        rows = connection.execute(
            "SELECT id, revision, case_json FROM regression_cases "
            "WHERE project_id = %s ORDER BY created_at, id LIMIT 2000",
            (project_id,),
        ).fetchall()
    cases = [
        {
            "id": str(row["id"]),
            "input": row["case_json"]["input"],
            "expected": row["case_json"]["expect"],
            "source_trace_id": row["case_json"]["source_trace_id"],
        }
        for row in rows
    ]
    revisions = [(str(row["id"]), row["revision"]) for row in rows]
    revision = hashlib.sha256(canonical_json(revisions).encode()).hexdigest()
    return {"revision": f"sha256:{revision}", "cases": cases}


@router.get("/regressions")
def list_regressions(
    project_id: uuid.UUID,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(load_settings),
) -> list[dict[str, Any]]:
    with postgres(settings) as connection:
        rows = connection.execute(
            "SELECT id, name, source_trace_id, cluster_signature, revision, case_json, "
            "created_at FROM regression_cases WHERE project_id = %s "
            "ORDER BY created_at DESC LIMIT 200",
            (project_id,),
        ).fetchall()
    return jsonable_encoder(rows)


@router.post("/datasets", status_code=201)
def create_dataset(
    project_id: uuid.UUID,
    data: DatasetInput,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(load_settings),
) -> dict[str, str]:
    dataset_id = uuid.uuid4()
    with postgres(settings) as connection:
        connection.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            (advisory_lock_key("dataset-name", project_id, data.name),),
        )
        if connection.execute(
            "SELECT 1 FROM datasets WHERE project_id = %s AND name = %s",
            (project_id, data.name),
        ).fetchone():
            raise HTTPException(409, "Dataset already exists")
        connection.execute(
            "INSERT INTO datasets(id, project_id, name) VALUES (%s, %s, %s)",
            (dataset_id, project_id, data.name),
        )
    return {"id": str(dataset_id)}


@router.get("/datasets")
def list_datasets(
    project_id: uuid.UUID,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(load_settings),
) -> list[dict[str, Any]]:
    with postgres(settings) as connection:
        rows = connection.execute(
            "SELECT id, name, revision, created_at FROM datasets WHERE project_id = %s "
            "ORDER BY created_at DESC LIMIT 100",
            (project_id,),
        ).fetchall()
    return jsonable_encoder(rows)


@router.post("/datasets/{dataset_id}/items", status_code=201)
def add_dataset_item(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    data: DatasetItemInput,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(load_settings),
) -> dict[str, str]:
    item_id = uuid.uuid4()
    with postgres(settings) as connection:
        with connection.transaction():
            dataset = connection.execute(
                "UPDATE datasets SET revision = revision + 1 WHERE id = %s AND project_id = %s "
                "RETURNING id",
                (dataset_id, project_id),
            ).fetchone()
            if not dataset:
                raise HTTPException(404, "Dataset not found")
            connection.execute(
                "INSERT INTO dataset_items(id, dataset_id, input_json, expected_json) "
                "VALUES (%s, %s, %s, %s)",
                (item_id, dataset_id, json.dumps(data.input), json.dumps(data.expected)),
            )
    return {"id": str(item_id)}


@router.get("/datasets/{dataset_id}/items")
def list_dataset_items(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(load_settings),
) -> list[dict[str, Any]]:
    with postgres(settings) as connection:
        rows = connection.execute(
            "SELECT i.id, i.input_json, i.expected_json FROM dataset_items i "
            "JOIN datasets d ON d.id = i.dataset_id "
            "WHERE d.project_id = %s AND d.id = %s ORDER BY i.created_at LIMIT 2000",
            (project_id, dataset_id),
        ).fetchall()
    return jsonable_encoder(rows)


@router.post("/release-evidence", status_code=201)
def create_release_evidence(
    project_id: uuid.UUID,
    data: ReleaseInput,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(load_settings),
) -> dict[str, Any]:
    try:
        bundle = release_evidence(data.baseline, data.candidate, data.policy, data.manifest)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    evidence_id = uuid.uuid4()
    with postgres(settings) as connection:
        row = connection.execute(
            "INSERT INTO release_evidence(id, project_id, evidence_sha256, bundle_json) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (project_id, evidence_sha256) DO NOTHING RETURNING id",
            (evidence_id, project_id, bundle["sha256"], json.dumps(bundle)),
        ).fetchone()
        if not row:
            row = connection.execute(
                "SELECT id FROM release_evidence WHERE project_id = %s AND evidence_sha256 = %s",
                (project_id, bundle["sha256"]),
            ).fetchone()
    if row is None:
        raise RuntimeError("Release evidence was not persisted")
    return {"id": str(row["id"]), "sha256": bundle["sha256"], "decision": bundle["decision"]}


@router.get("/release-evidence")
def list_release_evidence(
    project_id: uuid.UUID,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(load_settings),
) -> list[dict[str, Any]]:
    with postgres(settings) as connection:
        rows = connection.execute(
            "SELECT id, created_at, evidence_sha256, "
            "bundle_json->'manifest' AS manifest, bundle_json->'decision' AS decision "
            "FROM release_evidence WHERE project_id = %s "
            "ORDER BY created_at DESC LIMIT 100",
            (project_id,),
        ).fetchall()
    return jsonable_encoder(rows)


@router.get("/release-evidence/{evidence_id}")
def get_release_evidence(
    project_id: uuid.UUID,
    evidence_id: uuid.UUID,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(load_settings),
) -> dict[str, Any]:
    with postgres(settings) as connection:
        row = connection.execute(
            "SELECT bundle_json FROM release_evidence WHERE project_id = %s AND id = %s",
            (project_id, evidence_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Release evidence not found")
    return row["bundle_json"]
