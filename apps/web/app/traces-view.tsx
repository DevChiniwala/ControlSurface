"use client";

import {
  Activity,
  ArrowRight,
  Clock3,
  Coins,
  RefreshCw,
  Search,
  Target,
} from "lucide-react";
import type { ReactNode } from "react";
import {
  displayDuration,
  displayRelativeDate,
  displayTokens,
  displayUsd,
  shortId,
} from "./format";
import type { Trace } from "./product-types";
import {
  EmptyState,
  MetricCard,
  PageHeader,
  StatusBadge,
} from "./ui-primitives";

export function TracesView({
  traces,
  loading,
  search,
  onSearch,
  selectedTraceId,
  onOpenTrace,
  onRefresh,
  detailPanel,
}: {
  traces: Trace[] | null;
  loading: boolean;
  search: string;
  onSearch: (value: string) => void;
  selectedTraceId?: string;
  onOpenTrace: (traceId: string) => void;
  onRefresh: () => void;
  detailPanel?: ReactNode;
}) {
  const rows = traces || [];
  const successful = rows.filter((trace) => trace.status === "success").length;
  const measuredDurations = rows
    .map((trace) => trace.duration_ms)
    .filter((value): value is number => value != null);
  const measuredCosts = rows
    .map((trace) => trace.cost_nano_usd)
    .filter((value): value is number => value != null);
  const averageDuration = measuredDurations.length
    ? measuredDurations.reduce((sum, value) => sum + value, 0) /
      measuredDurations.length
    : null;
  const totalCost = measuredCosts.length
    ? measuredCosts.reduce((sum, value) => sum + value, 0)
    : null;

  return (
    <section
      className="feature-page traces-page"
      aria-labelledby="traces-title"
    >
      <PageHeader
        eyebrow="OBSERVE / EXECUTIONS"
        title="Traces"
        description="Observe and debug every agent execution."
        action={
          <button className="button subtle" onClick={onRefresh}>
            <RefreshCw size={15} /> Refresh
          </button>
        }
      />
      <div className="trace-toolbar" role="search">
        <Search size={16} aria-hidden="true" />
        <input
          value={search}
          onChange={(event) => onSearch(event.target.value)}
          placeholder="Search traces, agents, or run IDs..."
          aria-label="Search traces"
        />
      </div>
      <div className="trace-summary-grid">
        <MetricCard
          icon={Activity}
          label="Loaded runs"
          value={rows.length.toLocaleString()}
          context="Latest matching executions"
        />
        <MetricCard
          icon={Target}
          label="Success rate"
          value={
            rows.length
              ? `${((successful / rows.length) * 100).toFixed(1)}%`
              : "—"
          }
          context="Across loaded runs"
          tone="success"
        />
        <MetricCard
          icon={Clock3}
          label="Average duration"
          value={displayDuration(averageDuration)}
          context="Recorded duration only"
          tone="cyan"
        />
        <MetricCard
          icon={Coins}
          label="Recorded cost"
          value={displayUsd(totalCost, 4)}
          context="Loaded runs with cost data"
        />
      </div>
      <div className="trace-workspace">
        <div className="panel trace-list-panel">
          <div className="panel-heading compact">
            <div>
              <h2>Agent runs</h2>
              <p>Select a run to inspect its execution graph and telemetry.</p>
            </div>
            <span className="panel-count">{rows.length} loaded</span>
          </div>
          {loading ? (
            <div className="table-skeleton" aria-label="Loading traces">
              {Array.from({ length: 8 }, (_, index) => (
                <div className="skeleton-row" key={index} />
              ))}
            </div>
          ) : rows.length ? (
            <div className="table-scroll trace-table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Run</th>
                    <th>State</th>
                    <th>Agent</th>
                    <th className="numeric">Spans</th>
                    <th className="numeric">Duration</th>
                    <th className="numeric">Tokens</th>
                    <th className="numeric">Cost</th>
                    <th>Started</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((trace) => {
                    const tokens =
                      trace.input_tokens == null && trace.output_tokens == null
                        ? null
                        : (trace.input_tokens || 0) +
                          (trace.output_tokens || 0);
                    return (
                      <tr
                        key={trace.trace_id}
                        className={`clickable ${selectedTraceId === trace.trace_id ? "selected" : ""}`}
                        onClick={() => onOpenTrace(trace.trace_id)}
                      >
                        <td>
                          <button
                            className="run-cell"
                            onClick={() => onOpenTrace(trace.trace_id)}
                          >
                            <strong>{trace.root_name || "Agent run"}</strong>
                            <span className="mono">
                              {shortId(trace.trace_id, 12)}
                            </span>
                          </button>
                        </td>
                        <td>
                          <StatusBadge value={trace.status} />
                        </td>
                        <td>{trace.agent_name || "—"}</td>
                        <td className="numeric">
                          {trace.span_count.toLocaleString()}
                        </td>
                        <td className="numeric">
                          {displayDuration(trace.duration_ms)}
                        </td>
                        <td className="numeric">{displayTokens(tokens)}</td>
                        <td className="numeric">
                          {displayUsd(trace.cost_nano_usd)}
                        </td>
                        <td>{displayRelativeDate(trace.start_time)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="No traces yet"
              description="Instrument an agent with the Python SDK to send your first production run."
            />
          )}
        </div>
        <aside
          className="panel trace-inspector-shell"
          aria-label="Trace inspector"
        >
          {detailPanel || (
            <div className="inspector-empty">
              <Activity size={28} strokeWidth={1.5} />
              <h2>Select a trace</h2>
              <p>
                Inspect execution steps, agent events, tool calls, timing, and
                recorded cost.
              </p>
              {rows[0] && (
                <button
                  className="button subtle"
                  onClick={() => onOpenTrace(rows[0].trace_id)}
                >
                  Inspect latest <ArrowRight size={15} />
                </button>
              )}
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}
