"use client";

import { useState } from "react";

type Attributes = Record<string, unknown>;
export type InspectedSpan = {
  span_id: string;
  name: string;
  operation: string;
  status: string;
  start_ns: number;
  end_ns: number;
  attributes: Attributes;
  events: Attributes[];
  input_tokens: number;
  output_tokens: number;
  cost_nano_usd: number;
};
type Section = { id: string; label: string; value?: unknown };

function first(attributes: Attributes, names: string[]): unknown {
  for (const name of names) {
    if (attributes[name] !== undefined && attributes[name] !== null)
      return attributes[name];
  }
  return undefined;
}

function matching(attributes: Attributes, prefixes: string[]): Attributes {
  return Object.fromEntries(
    Object.entries(attributes).filter(([key]) =>
      prefixes.some((prefix) => key.startsWith(prefix)),
    ),
  );
}

function readable(value: unknown): string {
  if (typeof value === "string") {
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }
  return JSON.stringify(value, null, 2) ?? "No captured value";
}

function sectionsFor(span: InspectedSpan): Section[] {
  const attrs = span.attributes;
  const sections: Section[] = [{ id: "overview", label: "Overview" }];
  const add = (id: string, label: string, value: unknown) => {
    if (
      value !== undefined &&
      value !== null &&
      !(Array.isArray(value) && !value.length) &&
      !(
        typeof value === "object" &&
        !Array.isArray(value) &&
        !Object.keys(value).length
      )
    ) {
      sections.push({ id, label, value });
    }
  };
  add(
    "input",
    "Input",
    first(attrs, [
      "controlsurface.input",
      "gen_ai.input.messages",
      "llm.input_messages",
      "input",
    ]),
  );
  add(
    "output",
    "Output",
    first(attrs, [
      "controlsurface.output",
      "gen_ai.output.messages",
      "llm.output_messages",
      "output",
    ]),
  );
  add(
    "prompt",
    "Prompt",
    first(attrs, [
      "controlsurface.prompt",
      "gen_ai.request.messages",
      "llm.prompts",
    ]),
  );
  add(
    "context",
    "Context",
    first(attrs, [
      "controlsurface.context",
      "controlsurface.retrieval.context",
    ]),
  );
  add(
    "model",
    "Model",
    matching(attrs, [
      "gen_ai.request.",
      "gen_ai.response.",
      "controlsurface.model.",
    ]),
  );
  if (span.operation === "model" || span.input_tokens || span.output_tokens) {
    add("tokens", "Tokens", {
      input_tokens: span.input_tokens,
      output_tokens: span.output_tokens,
    });
  }
  if (span.cost_nano_usd)
    add("cost", "Cost", {
      cost_usd: span.cost_nano_usd / 1_000_000_000,
      cost_nano_usd: span.cost_nano_usd,
    });
  add(
    "tool-args",
    "Tool args",
    first(attrs, [
      "controlsurface.tool.arguments",
      "gen_ai.tool.call.arguments",
      "gen_ai.tool.arguments",
    ]),
  );
  add(
    "tool-result",
    "Tool result",
    first(attrs, [
      "controlsurface.tool.result",
      "gen_ai.tool.call.result",
      "gen_ai.tool.result",
    ]),
  );
  if (span.operation === "retrieval")
    add(
      "retrieval",
      "Retrieval",
      matching(attrs, [
        "controlsurface.retrieval.",
        "db.",
        "gen_ai.retrieval.",
      ]),
    );
  if (span.status === "error") {
    add("errors", "Errors", {
      status: span.status,
      attributes: matching(attrs, ["error.", "exception."]),
      events: span.events.filter((event) =>
        /exception|error/i.test(String(event.name || "")),
      ),
    });
  }
  add("events", "Events", span.events);
  add("metadata", "Metadata", attrs);
  return sections;
}

export function SpanInspector({ span }: { span: InspectedSpan }) {
  const [selected, setSelected] = useState("overview");
  const sections = sectionsFor(span);
  const section = sections.find((item) => item.id === selected) || sections[0];
  return (
    <>
      <div className="span-detail-heading">
        <span className={`badge badge-${span.operation}`}>
          {span.operation}
        </span>
        <h3>{span.name}</h3>
        <span className="mono muted">{span.span_id}</span>
      </div>
      <div
        className="tabs contextual-tabs"
        role="tablist"
        aria-label="Span details"
      >
        {sections.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={section.id === item.id}
            aria-controls="span-tab-panel"
            className={section.id === item.id ? "active" : ""}
            onClick={() => setSelected(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div id="span-tab-panel" role="tabpanel" aria-label={section.label}>
        {section.id === "overview" ? (
          <div className="data-list">
            <div>
              <span>Status</span>
              <span className={`badge badge-${span.status}`}>
                {span.status}
              </span>
            </div>
            <div>
              <span>Operation</span>
              <strong>{span.operation}</strong>
            </div>
            <div>
              <span>Latency</span>
              <strong>
                {((span.end_ns - span.start_ns) / 1e6).toFixed(1)} ms
              </strong>
            </div>
            <div>
              <span>Input tokens</span>
              <strong>{span.input_tokens.toLocaleString()}</strong>
            </div>
            <div>
              <span>Output tokens</span>
              <strong>{span.output_tokens.toLocaleString()}</strong>
            </div>
            <div>
              <span>Cost</span>
              <strong>
                ${(span.cost_nano_usd / 1_000_000_000).toFixed(4)}
              </strong>
            </div>
          </div>
        ) : (
          <pre className="json-block">{readable(section.value)}</pre>
        )}
      </div>
    </>
  );
}
