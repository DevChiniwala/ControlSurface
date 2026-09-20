"use client";

import { useEffect, useRef, useState } from "react";
import { Plus, X } from "lucide-react";

type JsonObject = Record<string, unknown>;
export type DatasetRecord = {
  id: string;
  name: string;
  revision: number;
  created_at: string;
};
export type DatasetItemRecord = {
  id: string;
  input_json: JsonObject;
  expected_json: JsonObject;
};
export type EvidenceBundle = {
  sha256: string;
  manifest: JsonObject;
  policy: JsonObject;
  decision: JsonObject;
  baseline_results: JsonObject[];
  candidate_results: JsonObject[];
};

function usePanelFocus(onClose: () => void) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const callback = useRef(onClose);
  callback.current = onClose;
  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    closeRef.current?.focus();
    function keydown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        callback.current();
      }
      if (event.key !== "Tab" || !panelRef.current) return;
      const focusable = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(
          "button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), summary",
        ),
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", keydown);
    return () => {
      document.removeEventListener("keydown", keydown);
      previous?.focus();
    };
  }, []);
  return { closeRef, panelRef };
}

function parseObject(value: string): JsonObject {
  const parsed: unknown = JSON.parse(value);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Input and expected behavior must each be a JSON object.");
  }
  return parsed as JsonObject;
}

export function DatasetPanel({
  dataset,
  loadItems,
  saveItem,
  onSaved,
  onClose,
}: {
  dataset: DatasetRecord;
  loadItems: (datasetId: string) => Promise<DatasetItemRecord[]>;
  saveItem: (
    datasetId: string,
    input: JsonObject,
    expected: JsonObject,
  ) => Promise<void>;
  onSaved: () => void;
  onClose: () => void;
}) {
  const { closeRef, panelRef } = usePanelFocus(onClose);
  const [items, setItems] = useState<DatasetItemRecord[]>([]);
  const [revision, setRevision] = useState(dataset.revision);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [input, setInput] = useState('{\n  "message": ""\n}');
  const [expected, setExpected] = useState('{\n  "completion": true\n}');
  useEffect(() => {
    let active = true;
    void loadItems(dataset.id)
      .then((result) => {
        if (active) setItems(result);
      })
      .catch((cause) => {
        if (active) setError((cause as Error).message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [dataset.id, loadItems]);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    let parsedInput: JsonObject;
    let parsedExpected: JsonObject;
    try {
      parsedInput = parseObject(input);
      parsedExpected = parseObject(expected);
    } catch (cause) {
      setError((cause as Error).message);
      return;
    }
    setSaving(true);
    try {
      await saveItem(dataset.id, parsedInput, parsedExpected);
      setItems(await loadItems(dataset.id));
      setRevision((current) => current + 1);
      onSaved();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="detail-overlay">
      <section
        ref={panelRef}
        className="detail-panel inspector-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="dataset-title"
      >
        <div className="detail-top">
          <button
            ref={closeRef}
            className="icon-button"
            onClick={onClose}
            aria-label="Close dataset"
          >
            <X size={18} />
          </button>
          <span className="eyebrow">DATASET / REVISION {revision}</span>
        </div>
        <div className="detail-intro">
          <h2 id="dataset-title">{dataset.name}</h2>
          <div className="detail-meta">
            <span>{items.length} scenarios</span>
            <span>Changes create a new revision</span>
          </div>
        </div>
        <div className="inspector-content">
          <h3>Add a scenario</h3>
          <p className="muted">
            Expected behavior is reviewed before local evaluation; it is not
            inferred from the observed output.
          </p>
          <form className="inspector-form" onSubmit={submit}>
            <label>
              Input JSON
              <textarea
                required
                spellCheck={false}
                rows={5}
                value={input}
                onChange={(event) => setInput(event.target.value)}
              />
            </label>
            <label>
              Expected behavior JSON
              <textarea
                required
                spellCheck={false}
                rows={5}
                value={expected}
                onChange={(event) => setExpected(event.target.value)}
              />
            </label>
            {error && (
              <div className="form-error" role="alert">
                {error}
              </div>
            )}
            <button className="button primary" disabled={saving}>
              {saving ? "Saving…" : "Add item"}
              <Plus size={15} />
            </button>
          </form>
          <h3>Items</h3>
          {loading ? (
            <div className="skeleton-row" />
          ) : items.length ? (
            items.map((item, index) => (
              <div className="inspector-item" key={item.id}>
                <span className="eyebrow">SCENARIO {index + 1}</span>
                <div className="inspector-columns">
                  <div>
                    <span>INPUT</span>
                    <pre className="json-block">
                      {JSON.stringify(item.input_json, null, 2)}
                    </pre>
                  </div>
                  <div>
                    <span>EXPECTED</span>
                    <pre className="json-block">
                      {JSON.stringify(item.expected_json, null, 2)}
                    </pre>
                  </div>
                </div>
              </div>
            ))
          ) : (
            <p className="muted">No scenarios yet. Add the first item above.</p>
          )}
        </div>
      </section>
    </div>
  );
}

export function EvidencePanel({
  bundle,
  onClose,
}: {
  bundle: EvidenceBundle;
  onClose: () => void;
}) {
  const { closeRef, panelRef } = usePanelFocus(onClose);
  const { manifest, policy, decision } = bundle;
  const baseline = new Map(
    bundle.baseline_results.map((item) => [String(item.case_id), item]),
  );
  return (
    <div className="detail-overlay">
      <section
        ref={panelRef}
        className="detail-panel inspector-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-title"
      >
        <div className="detail-top">
          <button
            ref={closeRef}
            className="icon-button"
            onClick={onClose}
            aria-label="Close release evidence"
          >
            <X size={18} />
          </button>
          <span className="eyebrow">RELEASE EVIDENCE</span>
          <span
            className={`badge badge-${decision.passed ? "passed" : "blocked"}`}
          >
            {decision.passed ? "PASS" : "BLOCK"}
          </span>
        </div>
        <div className="detail-intro">
          <h2 id="evidence-title">{String(manifest.candidate_version)}</h2>
          <div className="detail-meta">
            <span>Baseline {String(manifest.baseline_version)}</span>
            <span>{bundle.candidate_results.length} paired cases</span>
          </div>
        </div>
        <div className="inspector-content">
          <div className="evidence-hash">
            <span>CONTENT SHA-256</span>
            <code>{bundle.sha256}</code>
          </div>
          <h3>Decision</h3>
          <div className="data-list">
            <div>
              <span>Policy</span>
              <strong>{String(policy.revision)}</strong>
            </div>
            <div>
              <span>Reasons</span>
              <strong>
                {Array.isArray(decision.reasons) && decision.reasons.length
                  ? decision.reasons.join(", ")
                  : "No violations"}
              </strong>
            </div>
            <div>
              <span>Regressed cases</span>
              <strong>
                {Array.isArray(decision.regressions)
                  ? decision.regressions.join(", ") || "None"
                  : "None"}
              </strong>
            </div>
            <div>
              <span>Tool accuracy</span>
              <strong>
                {(Number(decision.baseline_tool_accuracy) * 100).toFixed(1)}% →{" "}
                {(Number(decision.candidate_tool_accuracy) * 100).toFixed(1)}%
              </strong>
            </div>
            <div>
              <span>Quality delta</span>
              <strong>
                {(Number(decision.quality_delta) * 100).toFixed(1)} points
              </strong>
            </div>
            <div>
              <span>Latency delta</span>
              <strong>{Number(decision.latency_delta_ms).toFixed(1)} ms</strong>
            </div>
          </div>
          <h3>Pinned inputs</h3>
          <div className="data-list">
            <div>
              <span>Dataset revision</span>
              <strong>{String(manifest.dataset_revision)}</strong>
            </div>
            <div>
              <span>Regression suite</span>
              <strong className="mono">
                {String(manifest.suite_revision)}
              </strong>
            </div>
            <div>
              <span>Pricing revision</span>
              <strong>{String(manifest.pricing_version)}</strong>
            </div>
            <div>
              <span>Execution environment</span>
              <strong>{String(manifest.execution_environment)}</strong>
            </div>
          </div>
          <details>
            <summary>Full pinned manifest and policy</summary>
            <pre className="json-block">
              {JSON.stringify({ manifest, policy }, null, 2)}
            </pre>
          </details>
          <h3>Paired case results</h3>
          <div className="evidence-cases">
            {bundle.candidate_results.map((item) => {
              const before = baseline.get(String(item.case_id));
              return (
                <div className="inspector-item" key={String(item.case_id)}>
                  <strong>{String(item.case_id)}</strong>
                  <span
                    className={`badge badge-${item.passed ? "passed" : "blocked"}`}
                  >
                    {before?.passed ? "PASS" : "FAIL"} →{" "}
                    {item.passed ? "PASS" : "FAIL"}
                  </span>
                  <span>
                    Quality {String(before?.quality_score ?? "—")} →{" "}
                    {String(item.quality_score)}
                  </span>
                  <span>
                    Tool {before?.tool_correct ? "correct" : "incorrect"} →{" "}
                    {item.tool_correct ? "correct" : "incorrect"}
                  </span>
                </div>
              );
            })}
          </div>
          <p className="muted">
            Independently verifying the content hash can detect accidental
            changes; it does not protect against a database administrator
            rewriting both content and hash.
          </p>
        </div>
      </section>
    </div>
  );
}
