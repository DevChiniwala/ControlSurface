"use client";

import {
  AlertTriangle,
  ArrowRight,
  ChevronDown,
  ChevronRight,
  Clock3,
  Fingerprint,
  GitBranch,
  Layers3,
} from "lucide-react";
import { useMemo, useState } from "react";
import { displayDate, displayRelativeDate, shortId } from "./format";
import type { Cluster, TraceDetail } from "./product-types";
import { EmptyState, MetricCard, PageHeader } from "./ui-primitives";

function featureText(
  features: Record<string, unknown>,
  key: string,
  fallback = "—",
) {
  const value = features[key];
  return value == null || value === "" ? fallback : String(value);
}

function categoryFor(cluster: Cluster) {
  return featureText(
    cluster.features,
    "failed_tool",
    featureText(
      cluster.features,
      "error_type",
      featureText(cluster.features, "termination_reason", "Other"),
    ),
  );
}

export function FailureClustersView({
  clusters,
  loading,
  onAnalyze,
  onCreateIncident,
  onOpenTrace,
  loadTrace,
}: {
  clusters: Cluster[] | null;
  loading: boolean;
  onAnalyze: () => void;
  onCreateIncident: (signature: string) => void;
  onOpenTrace: (traceId: string) => void;
  loadTrace: (traceId: string) => Promise<TraceDetail>;
}) {
  const rows = useMemo(() => clusters || [], [clusters]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [representatives, setRepresentatives] = useState<
    Record<string, TraceDetail | undefined>
  >({});
  const [loadingTrace, setLoadingTrace] = useState<string | null>(null);
  const total = rows.reduce((sum, cluster) => sum + cluster.count, 0);
  const latest = rows.reduce<string | null>(
    (value, cluster) =>
      !value || cluster.last_seen > value ? cluster.last_seen : value,
    null,
  );
  const distribution = useMemo(() => {
    const groups = new Map<string, number>();
    rows.forEach((cluster) =>
      groups.set(
        categoryFor(cluster),
        (groups.get(categoryFor(cluster)) || 0) + cluster.count,
      ),
    );
    return [...groups.entries()]
      .sort((left, right) => right[1] - left[1])
      .slice(0, 5);
  }, [rows]);

  async function toggle(cluster: Cluster) {
    if (expanded === cluster.signature) {
      setExpanded(null);
      return;
    }
    setExpanded(cluster.signature);
    const representative = cluster.representatives[0];
    if (!representative || representatives[cluster.signature]) return;
    setLoadingTrace(cluster.signature);
    try {
      const detail = await loadTrace(representative.trace_id);
      setRepresentatives((current) => ({
        ...current,
        [cluster.signature]: detail,
      }));
    } finally {
      setLoadingTrace(null);
    }
  }

  return (
    <section
      className="feature-page clusters-page"
      aria-labelledby="failure-clusters-title"
    >
      <PageHeader
        eyebrow="DIAGNOSE / FAILURE INTELLIGENCE"
        title="Failure Clusters"
        description="Group recurring production failures by execution pattern and inspectable evidence."
        action={
          <button className="button primary" onClick={onAnalyze}>
            <Fingerprint size={16} /> Analyze failures
          </button>
        }
      />
      <div className="cluster-summary-grid">
        <MetricCard
          icon={AlertTriangle}
          label="Sampled failed runs"
          value={total.toLocaleString()}
          context="Across returned signatures"
          tone="danger"
        />
        <MetricCard
          icon={GitBranch}
          label="Distinct signatures"
          value={rows.length.toLocaleString()}
          context="Deterministic failure groups"
          tone="cyan"
        />
        <MetricCard
          icon={Clock3}
          label="Latest failed run"
          value={displayRelativeDate(latest)}
          context={displayDate(latest)}
        />
        <div className="metric-card cluster-distribution-card">
          <div className="metric-card-label">
            <span className="metric-icon">
              <Layers3 size={16} />
            </span>
            <span>Failure distribution</span>
          </div>
          {distribution.length ? (
            <>
              <div className="segmented-bar" aria-label="Failure distribution">
                {distribution.map(([name, count], index) => (
                  <span
                    key={name}
                    className={`segment segment-${index}`}
                    style={{ width: `${total ? (count / total) * 100 : 0}%` }}
                    title={`${name}: ${count}`}
                  />
                ))}
              </div>
              <div className="segment-legend">
                {distribution.slice(0, 3).map(([name, count], index) => (
                  <span key={name}>
                    <i className={`segment-key segment-${index}`} />
                    {name}{" "}
                    {total ? `${((count / total) * 100).toFixed(0)}%` : "—"}
                  </span>
                ))}
              </div>
            </>
          ) : (
            <small>No failure population available</small>
          )}
        </div>
      </div>
      <div className="cluster-toolbar">
        <span>Failure signatures</span>
        <small>{rows.length} groups ordered by affected runs</small>
      </div>
      {loading ? (
        <div
          className="panel table-skeleton"
          aria-label="Loading failure clusters"
        >
          {Array.from({ length: 7 }, (_, index) => (
            <div className="skeleton-row" key={index} />
          ))}
        </div>
      ) : rows.length ? (
        <div className="cluster-list">
          {rows.map((cluster, index) => {
            const isExpanded = expanded === cluster.signature;
            const detail = representatives[cluster.signature];
            const sequence = Array.isArray(cluster.features.tool_sequence)
              ? cluster.features.tool_sequence.map(String)
              : [];
            const failureName = categoryFor(cluster);
            return (
              <article
                className={`panel failure-cluster ${isExpanded ? "expanded" : ""}`}
                key={cluster.signature}
              >
                <div className="cluster-row">
                  <button
                    className="cluster-title"
                    onClick={() => void toggle(cluster)}
                    aria-expanded={isExpanded}
                  >
                    <span className="cluster-rank">
                      C{String(index + 1).padStart(3, "0")}
                    </span>
                    <span>
                      <strong>{failureName}</strong>
                      <small className="mono">
                        {shortId(cluster.signature, 16)}
                      </small>
                    </span>
                  </button>
                  <div>
                    <small>Affected runs</small>
                    <strong>{cluster.count.toLocaleString()}</strong>
                  </div>
                  <div>
                    <small>First seen</small>
                    <strong>{displayRelativeDate(cluster.first_seen)}</strong>
                  </div>
                  <div>
                    <small>Retries</small>
                    <strong>
                      {featureText(cluster.features, "retry_count")}
                    </strong>
                  </div>
                  <div>
                    <small>Termination</small>
                    <strong>
                      {featureText(cluster.features, "termination_reason")}
                    </strong>
                  </div>
                  <div className="cluster-actions">
                    <button
                      className="button primary small"
                      onClick={() => onCreateIncident(cluster.signature)}
                    >
                      Create incident
                    </button>
                    <button
                      className="icon-button"
                      onClick={() => void toggle(cluster)}
                      aria-label={
                        isExpanded ? "Collapse cluster" : "Expand cluster"
                      }
                    >
                      {isExpanded ? (
                        <ChevronDown size={17} />
                      ) : (
                        <ChevronRight size={17} />
                      )}
                    </button>
                  </div>
                </div>
                {isExpanded && (
                  <div className="cluster-expanded">
                    <section>
                      <span className="pane-label">FAILURE EVIDENCE</span>
                      <h3>
                        {featureText(
                          cluster.features,
                          "error_type",
                          "Observed execution failure",
                        )}
                      </h3>
                      <p>
                        {featureText(
                          cluster.features,
                          "error_message",
                          "No normalized error message was recorded for this signature.",
                        )}
                      </p>
                      <dl className="evidence-facts">
                        <div>
                          <dt>Failed tool</dt>
                          <dd>
                            {featureText(cluster.features, "failed_tool")}
                          </dd>
                        </div>
                        <div>
                          <dt>Model</dt>
                          <dd>{featureText(cluster.features, "model")}</dd>
                        </div>
                        <div>
                          <dt>Provider</dt>
                          <dd>{featureText(cluster.features, "provider")}</dd>
                        </div>
                      </dl>
                    </section>
                    <section>
                      <span className="pane-label">
                        COMMON EXECUTION SEQUENCE
                      </span>
                      {sequence.length ? (
                        <ol className="sequence-list">
                          {sequence.slice(0, 8).map((step, stepIndex) => (
                            <li key={`${step}-${stepIndex}`}>
                              <span>{stepIndex + 1}</span>
                              <strong>{step}</strong>
                              {step ===
                                featureText(
                                  cluster.features,
                                  "failed_tool",
                                ) && <em>Failure step</em>}
                            </li>
                          ))}
                        </ol>
                      ) : (
                        <p className="muted">
                          No normalized tool sequence was recorded.
                        </p>
                      )}
                    </section>
                    <section>
                      <span className="pane-label">
                        REPRESENTATIVE EXECUTION
                      </span>
                      {loadingTrace === cluster.signature ? (
                        <div className="skeleton-row" />
                      ) : detail ? (
                        <div className="representative-trace">
                          {detail.spans.slice(0, 8).map((span) => (
                            <button
                              key={span.span_id}
                              className={span.status === "error" ? "error" : ""}
                              onClick={() => onOpenTrace(detail.trace_id)}
                            >
                              <span
                                className={`span-dot ${span.status === "error" ? "error" : span.operation}`}
                              />
                              <strong>{span.name}</strong>
                              <small>
                                {((span.end_ns - span.start_ns) / 1e6).toFixed(
                                  0,
                                )}
                                ms
                              </small>
                            </button>
                          ))}
                          <button
                            className="text-button representative-link"
                            onClick={() => onOpenTrace(detail.trace_id)}
                          >
                            View full trace <ArrowRight size={14} />
                          </button>
                        </div>
                      ) : (
                        <p className="muted">
                          No representative trace is available.
                        </p>
                      )}
                    </section>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      ) : (
        <div className="panel">
          <EmptyState
            title="No failures to cluster"
            description="Failed agent runs will be grouped here as telemetry arrives."
          />
        </div>
      )}
    </section>
  );
}
