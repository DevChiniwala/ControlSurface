"use client";

import {
  ArrowRight,
  CheckCircle2,
  Clock3,
  Hash,
  ShieldAlert,
} from "lucide-react";
import type { ReactNode } from "react";
import { displayDate, displayDelta, shortId } from "./format";
import type { ReleaseSummary } from "./product-types";
import {
  EmptyState,
  MetricCard,
  PageHeader,
  StatusBadge,
} from "./ui-primitives";

function compactVersion(value: string) {
  return value.length > 30 ? `${value.slice(0, 20)}…${value.slice(-7)}` : value;
}

export function ReleaseGatesView({
  releases,
  loading,
  selectedId,
  onSelect,
  detailPanel,
}: {
  releases: ReleaseSummary[] | null;
  loading: boolean;
  selectedId?: string;
  onSelect: (id: string) => void;
  detailPanel?: ReactNode;
}) {
  const rows = releases || [];
  const passed = rows.filter((item) => item.decision === "passed").length;
  const blocked = rows.length - passed;
  const failedGates = rows.reduce(
    (sum, item) => sum + item.failed_gate_count,
    0,
  );

  return (
    <section
      className="feature-page release-page"
      aria-labelledby="release-gates-title"
    >
      <PageHeader
        eyebrow="SHIP / DECISIONS"
        title="Release Gates"
        description="Prevent regressions and ship candidates with reproducible evidence."
      />
      <div className="release-summary-grid">
        <MetricCard
          icon={CheckCircle2}
          label="Pass rate"
          value={
            rows.length ? `${((passed / rows.length) * 100).toFixed(0)}%` : "—"
          }
          context={`${passed} passed decisions`}
          tone="success"
        />
        <MetricCard
          icon={ShieldAlert}
          label="Blocked candidates"
          value={blocked.toLocaleString()}
          context={`${rows.length} total decisions`}
          tone={blocked ? "danger" : "blue"}
        />
        <MetricCard
          icon={Clock3}
          label="Total decisions"
          value={rows.length.toLocaleString()}
          context="Immutable gate evaluations"
        />
        <MetricCard
          icon={Hash}
          label="Failed gates"
          value={failedGates.toLocaleString()}
          context="Across loaded decisions"
          tone={failedGates ? "warning" : "cyan"}
        />
      </div>
      <div className="release-workspace">
        <div className="panel release-list-panel">
          <div className="panel-heading compact">
            <div>
              <h2>Release decisions</h2>
              <p>Candidate comparisons and gate outcomes.</p>
            </div>
            <span className="panel-count">{rows.length} decisions</span>
          </div>
          {loading ? (
            <div
              className="table-skeleton"
              aria-label="Loading release decisions"
            >
              {Array.from({ length: 7 }, (_, index) => (
                <div className="skeleton-row" key={index} />
              ))}
            </div>
          ) : rows.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Candidate</th>
                    <th>Baseline</th>
                    <th>Status</th>
                    <th className="numeric">Quality</th>
                    <th className="numeric">Cost</th>
                    <th className="numeric">Latency</th>
                    <th className="numeric">Tools</th>
                    <th>Evidence</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((item) => (
                    <tr
                      key={item.id}
                      className={`clickable ${selectedId === item.id ? "selected" : ""}`}
                      onClick={() => onSelect(item.id)}
                    >
                      <td>
                        <button
                          className="run-cell"
                          onClick={() => onSelect(item.id)}
                        >
                          <strong title={item.candidate_version}>
                            {compactVersion(item.candidate_version)}
                          </strong>
                          <span className="mono">{shortId(item.id, 10)}</span>
                        </button>
                      </td>
                      <td className="mono muted" title={item.baseline_version}>
                        {compactVersion(item.baseline_version)}
                      </td>
                      <td>
                        <StatusBadge value={item.decision} />
                      </td>
                      <DeltaCell value={item.quality_delta} />
                      <DeltaCell value={item.cost_delta} inverse />
                      <DeltaCell value={item.latency_delta} inverse />
                      <DeltaCell value={item.tool_accuracy_delta} />
                      <td className="mono" title={item.evidence_hash}>
                        {shortId(item.evidence_hash, 10)}
                      </td>
                      <td>{displayDate(item.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="No release decisions"
              description="Run a release gate to freeze a reproducible comparison and its evidence bundle."
            />
          )}
        </div>
        <aside
          className="panel release-detail-shell"
          aria-label="Release decision detail"
        >
          {detailPanel || (
            <div className="inspector-empty">
              <ShieldAlert size={28} strokeWidth={1.5} />
              <h2>Select a decision</h2>
              <p>
                Review thresholds, observed deltas, decision reasons, and
                immutable inputs.
              </p>
              {rows[0] && (
                <button
                  className="button subtle"
                  onClick={() => onSelect(rows[0].id)}
                >
                  Review latest <ArrowRight size={15} />
                </button>
              )}
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}

function DeltaCell({
  value,
  inverse = false,
}: {
  value: number | null;
  inverse?: boolean;
}) {
  const positive = value != null && (inverse ? value <= 0 : value >= 0);
  const negative = value != null && (inverse ? value > 0 : value < 0);
  return (
    <td
      className={`numeric delta ${positive ? "positive" : negative ? "negative" : ""}`}
    >
      {displayDelta(value, { percent: true })}
    </td>
  );
}
