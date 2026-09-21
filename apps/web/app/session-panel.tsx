"use client";

import { useState } from "react";
import { ArrowRight, Search, X } from "lucide-react";
import { usePanelFocus } from "./use-panel-focus";

export type SessionSummary = {
  session_id: string;
  trace_count: number;
  errors: number;
  cost_nano_usd: number;
  last_seen: string;
};

export type SessionRun = {
  trace_id: string;
  root_name: string;
  agent_name: string;
  status: string;
  duration_ms: number;
  span_count: number;
  cost_nano_usd: number;
  start_time: string;
};

function money(nano: number) {
  return `$${(nano / 1_000_000_000).toFixed(4)}`;
}

export function SessionPanel({
  session,
  runs,
  loading,
  onClose,
  onOpenTrace,
}: {
  session: SessionSummary;
  runs: SessionRun[];
  loading: boolean;
  onClose: () => void;
  onOpenTrace: (traceId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const { closeRef, panelRef } = usePanelFocus(onClose);
  const filtered = runs.filter((run) =>
    `${run.root_name} ${run.agent_name} ${run.trace_id}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );

  return (
    <div className="detail-overlay">
      <section
        className="detail-panel session-panel"
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="session-title"
      >
        <div className="detail-top">
          <button
            ref={closeRef}
            className="icon-button"
            onClick={onClose}
            aria-label="Close session"
          >
            <X size={18} />
          </button>
          <span className="eyebrow">OBSERVE / SESSION</span>
        </div>
        <div className="detail-intro">
          <h2 id="session-title">Session {session.session_id}</h2>
          <p className="muted">
            Ordered agent runs sharing this session identity.
          </p>
        </div>
        <div className="session-content">
          <div className="session-metrics">
            <div>
              <span>Runs</span>
              <strong>{session.trace_count}</strong>
            </div>
            <div>
              <span>Errors</span>
              <strong>{session.errors}</strong>
            </div>
            <div>
              <span>Recorded cost</span>
              <strong>{money(session.cost_nano_usd)}</strong>
            </div>
            <div>
              <span>Last activity</span>
              <strong>{new Date(session.last_seen).toLocaleString()}</strong>
            </div>
          </div>
          <label className="toolbar session-search">
            <Search size={16} />
            <input
              aria-label="Search session runs"
              placeholder="Search runs, agents, or trace IDs"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <span>{filtered.length} shown</span>
          </label>
          <div className="panel table-panel">
            {loading ? (
              <div className="skeleton-row" />
            ) : filtered.length ? (
              <table>
                <thead>
                  <tr>
                    <th>Run</th>
                    <th>Agent</th>
                    <th>Status</th>
                    <th>Duration</th>
                    <th>Steps</th>
                    <th>Cost</th>
                    <th>Started</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((run) => (
                    <tr key={run.trace_id}>
                      <td>
                        <button
                          className="text-button row-link strong"
                          onClick={() => onOpenTrace(run.trace_id)}
                        >
                          {run.root_name || run.trace_id.slice(0, 12)}
                        </button>
                        <span className="mono muted">
                          {run.trace_id.slice(0, 12)}…
                        </span>
                      </td>
                      <td>{run.agent_name || "—"}</td>
                      <td>
                        <span className={`badge badge-${run.status}`}>
                          {run.status}
                        </span>
                      </td>
                      <td>{run.duration_ms} ms</td>
                      <td>{run.span_count}</td>
                      <td>{money(run.cost_nano_usd)}</td>
                      <td>{new Date(run.start_time).toLocaleString()}</td>
                      <td>
                        <ArrowRight size={14} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty">
                <h3>
                  {query ? "No matching runs" : "No runs in this session"}
                </h3>
                <p>
                  {query
                    ? "Try a different agent, run name, or trace ID."
                    : "No trace summaries were returned for this session."}
                </p>
              </div>
            )}
          </div>
          {session.trace_count > runs.length && !loading && (
            <p className="session-limit">
              Showing the latest {runs.length} of {session.trace_count} runs.
              Narrow the session or use trace search for older activity.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
