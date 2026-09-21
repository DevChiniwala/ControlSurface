"use client";

import { useMemo, useState } from "react";
import type { InspectedSpan } from "./span-inspector";

const MAX_VISIBLE_EVENTS = 160;

function capturedValue(
  attributes: Record<string, unknown>,
  keys: string[],
): string | null {
  for (const key of keys) {
    const value = attributes[key];
    if (value === undefined || value === null || value === "") continue;
    const text = typeof value === "string" ? value : JSON.stringify(value);
    if (text) return text.length > 220 ? `${text.slice(0, 220)}…` : text;
  }
  return null;
}

function duration(span: InspectedSpan): string {
  const ms = Math.max(0, (span.end_ns - span.start_ns) / 1e6);
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${ms.toFixed(0)}ms`;
}

export function ExecutionFlow({
  spans,
  selectedId,
  onSelect,
}: {
  spans: InspectedSpan[];
  selectedId: string | undefined;
  onSelect: (id: string) => void;
}) {
  const [view, setView] = useState<"transcript" | "timeline">("transcript");
  const ordered = useMemo(
    () => [...spans].sort((a, b) => a.start_ns - b.start_ns),
    [spans],
  );
  const visible = ordered.slice(0, MAX_VISIBLE_EVENTS);
  const start = ordered[0]?.start_ns ?? 0;
  const end = ordered.reduce(
    (latest, span) => Math.max(latest, span.end_ns),
    start + 1,
  );
  const range = end - start;

  return (
    <section className="trace-flow" aria-label="Agent execution flow">
      <div className="trace-flow-header">
        <div>
          <span className="pane-label">AGENT EXECUTION</span>
          <strong>{ordered.length} events</strong>
        </div>
        <div
          className="trace-view-switch"
          role="group"
          aria-label="Execution view"
        >
          <button
            type="button"
            className={view === "transcript" ? "active" : ""}
            aria-pressed={view === "transcript"}
            onClick={() => setView("transcript")}
          >
            Transcript
          </button>
          <button
            type="button"
            className={view === "timeline" ? "active" : ""}
            aria-pressed={view === "timeline"}
            onClick={() => setView("timeline")}
          >
            Timeline
          </button>
        </div>
      </div>
      <div className="trace-flow-list">
        {visible.map((span, index) => {
          const input = capturedValue(span.attributes, [
            "controlsurface.input",
            "controlsurface.tool.arguments",
            "gen_ai.input.messages",
            "gen_ai.tool.call.arguments",
            "input",
          ]);
          const output = capturedValue(span.attributes, [
            "controlsurface.output",
            "controlsurface.tool.result",
            "gen_ai.output.messages",
            "gen_ai.tool.call.result",
            "output",
          ]);
          const left = Math.max(0, ((span.start_ns - start) / range) * 100);
          const width = Math.max(
            1,
            (Math.max(0, span.end_ns - span.start_ns) / range) * 100,
          );
          return (
            <button
              type="button"
              key={span.span_id}
              className={`trace-event ${span.span_id === selectedId ? "selected" : ""} ${span.status === "error" ? "has-error" : ""}`}
              aria-pressed={span.span_id === selectedId}
              onClick={() => onSelect(span.span_id)}
            >
              <span className="trace-event-step">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="trace-event-body">
                <span className="trace-event-head">
                  <span
                    className={`span-dot ${span.status === "error" ? "error" : span.operation}`}
                  />
                  <span className="trace-event-kind">{span.operation}</span>
                  <span className="trace-event-duration">{duration(span)}</span>
                </span>
                <strong>{span.name}</strong>
                {view === "transcript" ? (
                  <span className="trace-event-capture">
                    {input && (
                      <span>
                        <em>INPUT</em>
                        {input}
                      </span>
                    )}
                    {output && (
                      <span>
                        <em>OUTPUT</em>
                        {output}
                      </span>
                    )}
                    {!input && !output && span.status === "error" && (
                      <span>
                        <em>ERROR</em>Inspect error events and metadata →
                      </span>
                    )}
                  </span>
                ) : (
                  <span
                    className="trace-waterfall"
                    aria-label={`Starts ${((span.start_ns - start) / 1e6).toFixed(0)} milliseconds into run, lasts ${duration(span)}`}
                  >
                    <span
                      style={{
                        left: `${left}%`,
                        width: `${Math.min(width, 100 - left)}%`,
                      }}
                    />
                  </span>
                )}
              </span>
            </button>
          );
        })}
        {ordered.length > MAX_VISIBLE_EVENTS && (
          <p className="trace-flow-limit">
            Showing the first {MAX_VISIBLE_EVENTS} events. Select any span in
            the execution tree to inspect it.
          </p>
        )}
      </div>
    </section>
  );
}
