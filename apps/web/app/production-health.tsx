"use client";

import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BellRing,
  Clock3,
  PlayCircle,
  Target,
} from "lucide-react";
import {
  displayDuration,
  displayPercent,
  displayRelativeDate,
  displayTokens,
  displayUsd,
  shortId,
} from "./format";
import type { OverviewData } from "./product-types";
import {
  EmptyState,
  MetricCard,
  PageHeader,
  StatusBadge,
} from "./ui-primitives";

export function ProductionHealthView({
  data,
  loading,
  onOpenIncidents,
  onOpenIncident,
  onOpenTrace,
  onOpenTraces,
  onOpenKeys,
}: {
  data: OverviewData | null;
  loading: boolean;
  onOpenIncidents: () => void;
  onOpenIncident: (id: string) => void;
  onOpenTrace: (id: string) => void;
  onOpenTraces: () => void;
  onOpenKeys: () => void;
}) {
  const agents = data?.agents || [];
  const incidents = (data?.incidents || []).filter(
    (item) => item.status !== "resolved",
  );
  const recentRuns = (data?.traces || []).slice(0, 6);
  const fallbackRuns = agents.reduce((sum, agent) => sum + agent.runs, 0);
  const fallbackFailures = agents.reduce(
    (sum, agent) => sum + agent.failed_runs,
    0,
  );
  const summary = data?.summary || {
    agent_count: agents.length,
    healthy_agent_count: agents.filter((agent) => agent.health === "healthy")
      .length,
    observed_run_count: fallbackRuns,
    failed_run_count: fallbackFailures,
    completion_rate: fallbackRuns
      ? (fallbackRuns - fallbackFailures) / fallbackRuns
      : null,
    p95_latency_ms: null,
    recorded_cost_nano_usd: agents.some((agent) => agent.cost_nano_usd != null)
      ? agents.reduce((sum, agent) => sum + (agent.cost_nano_usd || 0), 0)
      : null,
  };

  return (
    <section
      className="feature-page production-health"
      aria-labelledby="production-health-title"
    >
      <PageHeader
        eyebrow="PRODUCTION / LAST 24 HOURS"
        title="Production Health"
        description="Live operational health across your AI agents."
        action={
          <button className="button subtle" onClick={onOpenIncidents}>
            View incidents <ArrowRight size={15} />
          </button>
        }
      />
      {loading ? (
        <div
          className="dashboard-skeleton"
          aria-label="Loading production health"
        >
          {Array.from({ length: 10 }, (_, index) => (
            <div className="skeleton-row" key={index} />
          ))}
        </div>
      ) : (
        <>
          <div className="health-metric-grid">
            <MetricCard
              icon={Activity}
              label="Agents healthy"
              value={
                <>
                  {summary.healthy_agent_count}
                  <span className="metric-total"> / {summary.agent_count}</span>
                </>
              }
              context="Passing active SLO classification"
              tone="success"
            />
            <MetricCard
              icon={PlayCircle}
              label="Observed runs"
              value={summary.observed_run_count.toLocaleString()}
              context={`Measured in the last ${data?.window_hours ?? 24}h`}
            />
            <MetricCard
              icon={AlertTriangle}
              label="Failed runs"
              value={summary.failed_run_count.toLocaleString()}
              context={
                summary.observed_run_count
                  ? `${((summary.failed_run_count / summary.observed_run_count) * 100).toFixed(1)}% of observed runs`
                  : "No runs observed"
              }
              tone="danger"
            />
            <MetricCard
              icon={BellRing}
              label="Open incidents"
              value={data?.open_incidents ?? 0}
              context={
                data?.open_incidents
                  ? "Requires investigation"
                  : "No active response"
              }
              tone={data?.open_incidents ? "warning" : "blue"}
            />
            <MetricCard
              icon={Target}
              label="Completion rate"
              value={displayPercent(summary.completion_rate)}
              context="Successful runs / observed runs"
              tone="cyan"
            />
            <MetricCard
              icon={Clock3}
              label="P95 latency"
              value={displayDuration(summary.p95_latency_ms)}
              context="Across the complete run population"
            />
          </div>

          <div className="overview-grid">
            <div className="panel overview-health-panel">
              <div className="panel-heading">
                <div>
                  <h2>
                    <span className="heading-status-dot healthy" /> Agent Health
                  </h2>
                  <p>SLO-backed state from production behavior.</p>
                </div>
                <span className="panel-count">{agents.length} agents</span>
              </div>
              {agents.length ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Agent</th>
                        <th>Status</th>
                        <th className="numeric">Success</th>
                        <th className="numeric">P95</th>
                        <th className="numeric">Runs</th>
                        <th className="numeric">Cost/run</th>
                        <th className="numeric">Errors</th>
                      </tr>
                    </thead>
                    <tbody>
                      {agents.map((agent) => (
                        <tr key={agent.agent_name}>
                          <td className="strong agent-cell">
                            <span className="agent-glyph">
                              {agent.agent_name.slice(0, 1).toUpperCase()}
                            </span>
                            {agent.agent_name || "Unnamed agent"}
                          </td>
                          <td>
                            <StatusBadge value={agent.health} />
                          </td>
                          <td className="numeric">
                            {displayPercent(agent.completion_rate)}
                          </td>
                          <td className="numeric">
                            {displayDuration(agent.p95_latency_ms)}
                          </td>
                          <td className="numeric">
                            {agent.runs.toLocaleString()}
                          </td>
                          <td className="numeric">
                            {displayUsd(agent.average_cost_nano_usd)}
                          </td>
                          <td className="numeric">
                            {displayPercent(
                              agent.runs
                                ? agent.failed_runs / agent.runs
                                : null,
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyState
                  title="No agent runs yet"
                  description="Create an API key and instrument an agent to populate production health."
                  action={
                    <button className="button subtle" onClick={onOpenKeys}>
                      Set up an API key <ArrowRight size={15} />
                    </button>
                  }
                />
              )}
            </div>

            <div className="panel overview-incidents-panel">
              <div className="panel-heading">
                <div>
                  <h2>
                    <span className="heading-status-dot incident" /> Active
                    Incidents
                  </h2>
                  <p>Current reliability investigations.</p>
                </div>
                <button className="text-button" onClick={onOpenIncidents}>
                  View all
                </button>
              </div>
              {incidents.length ? (
                <div className="overview-incidents">
                  {incidents.slice(0, 4).map((item) => (
                    <button
                      key={item.id}
                      onClick={() => onOpenIncident(item.id)}
                    >
                      <span className="overview-incident-top">
                        <span className="mono">
                          INC-{shortId(item.id, 6).replace("…", "")}
                        </span>
                        <StatusBadge value={item.severity} />
                      </span>
                      <strong>{item.title}</strong>
                      <span className="incident-agent-line">
                        {item.agent_name || "Agent unavailable"} ·{" "}
                        {item.affected_run_count.toLocaleString()} runs
                      </span>
                      {item.top_evidence_subject && (
                        <span className="incident-evidence-line">
                          Likely correlation: <b>{item.top_evidence_subject}</b>
                          {item.top_evidence_score != null &&
                            ` · ${item.top_evidence_score.toFixed(2)}`}
                        </span>
                      )}
                      <span>{displayRelativeDate(item.started_at)}</span>
                    </button>
                  ))}
                </div>
              ) : (
                <EmptyState
                  title="No active incidents"
                  description="New incidents appear after a failure cluster is investigated."
                />
              )}
            </div>
          </div>

          <div className="panel overview-runs">
            <div className="panel-heading">
              <div>
                <h2>Recent Agent Runs</h2>
                <p>Latest processed execution summaries.</p>
              </div>
              <button className="text-button" onClick={onOpenTraces}>
                View all runs
              </button>
            </div>
            {recentRuns.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Run</th>
                      <th>Agent</th>
                      <th>Status</th>
                      <th className="numeric">Latency</th>
                      <th className="numeric">Steps</th>
                      <th className="numeric">Tokens</th>
                      <th className="numeric">Cost</th>
                      <th>Started</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentRuns.map((trace) => {
                      const tokens =
                        trace.input_tokens == null &&
                        trace.output_tokens == null
                          ? null
                          : (trace.input_tokens || 0) +
                            (trace.output_tokens || 0);
                      return (
                        <tr
                          key={trace.trace_id}
                          className="clickable"
                          onClick={() => onOpenTrace(trace.trace_id)}
                        >
                          <td>
                            <button className="text-button row-link strong">
                              {trace.root_name || shortId(trace.trace_id)}
                            </button>
                          </td>
                          <td>{trace.agent_name || "—"}</td>
                          <td>
                            <StatusBadge value={trace.status} />
                          </td>
                          <td className="numeric">
                            {displayDuration(trace.duration_ms)}
                          </td>
                          <td className="numeric">{trace.span_count}</td>
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
                title="No recent runs"
                description="Instrument an agent to see production activity here."
              />
            )}
          </div>
        </>
      )}
    </section>
  );
}
