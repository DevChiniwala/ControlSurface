import { Activity, AlertTriangle, Check, GitBranch } from "lucide-react";
import { BrandMark } from "./brand";

const runRows = [
  {
    name: "support-agent",
    detail: "Customer request",
    time: "2.1s",
    error: false,
  },
  {
    name: "research-agent",
    detail: "Policy lookup",
    time: "4.8s",
    error: false,
  },
  {
    name: "refund.execute",
    detail: "Tool contract",
    time: "4.1s",
    error: true,
  },
];

export function AuthVisual() {
  return (
    <aside className="auth-showcase">
      <div className="auth-preview-caption">Illustrative product preview</div>
      <div className="auth-preview-scene" aria-hidden="true">
        <div className="auth-preview-glow" />
        <div className="auth-preview-window">
          <div className="auth-preview-rail">
            <BrandMark />
            <span className="rail-active">
              <Activity size={15} />
            </span>
            <span>
              <GitBranch size={15} />
            </span>
            <span>
              <AlertTriangle size={15} />
            </span>
          </div>
          <div className="auth-preview-dashboard">
            <header className="preview-topline">
              <div>
                <span>Production Health</span>
                <small>Operational health across your AI agents</small>
              </div>
              <span className="preview-range">Last 24 hours</span>
            </header>
            <div className="preview-metrics">
              <div>
                <span>Agents healthy</span>
                <strong>11 / 13</strong>
                <small>Across production</small>
              </div>
              <div>
                <span>Success rate</span>
                <strong>98.2%</strong>
                <svg viewBox="0 0 70 18" aria-hidden="true">
                  <path d="M1 14 12 11 23 13 35 6 45 8 55 3 69 5" />
                </svg>
              </div>
              <div>
                <span>P95 latency</span>
                <strong>1.3s</strong>
                <svg viewBox="0 0 70 18" aria-hidden="true">
                  <path d="M1 5 12 7 23 4 35 11 45 9 55 12 69 8" />
                </svg>
              </div>
              <div>
                <span>Open incidents</span>
                <strong>2</strong>
                <small>1 needs review</small>
              </div>
            </div>
            <div className="preview-columns">
              <div className="preview-panel preview-health">
                <div className="preview-panel-heading">
                  <span>Agent Health</span>
                  <small>3 agents</small>
                </div>
                <div className="preview-health-row">
                  <span>SupportAgent</span>
                  <i>
                    <b style={{ width: "91%" }} />
                  </i>
                  <em>99.1%</em>
                </div>
                <div className="preview-health-row">
                  <span>ResearchAgent</span>
                  <i>
                    <b className="warn" style={{ width: "68%" }} />
                  </i>
                  <em>94.2%</em>
                </div>
                <div className="preview-health-row">
                  <span>BillingAgent</span>
                  <i>
                    <b style={{ width: "86%" }} />
                  </i>
                  <em>98.8%</em>
                </div>
              </div>
              <div className="preview-panel preview-incident">
                <div className="preview-panel-heading">
                  <span>Active incident</span>
                  <small>INC-281</small>
                </div>
                <strong>RefundAgent degradation</strong>
                <p>Tool success fell after a schema change.</p>
                <div>
                  <span className="preview-severity-dot" /> High severity{" "}
                  <span className="preview-incident-arrow">↗</span>
                </div>
              </div>
            </div>
            <div className="preview-panel preview-runs">
              <div className="preview-panel-heading">
                <span>Recent agent runs</span>
                <small>View traces ↗</small>
              </div>
              {runRows.map((row) => (
                <div className="preview-run" key={row.name}>
                  <span
                    className={
                      row.error ? "preview-run-dot error" : "preview-run-dot"
                    }
                  />
                  <span>
                    <strong>{row.name}</strong>
                    <small>{row.detail}</small>
                  </span>
                  <em>{row.time}</em>
                  {row.error ? (
                    <AlertTriangle size={13} />
                  ) : (
                    <Check size={13} />
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="preview-gate">
          <div>
            <span className="preview-gate-icon">
              <GitBranch size={16} />
            </span>
            <strong>Release Gate</strong>
            <small>Candidate v19</small>
          </div>
          <span>
            <Check size={13} /> Quality <em>Pass</em>
          </span>
          <span>
            <Check size={13} /> Cost <em>Pass</em>
          </span>
          <span className="gate-warning">
            <AlertTriangle size={13} /> Tool reliability <em>Review</em>
          </span>
        </div>
      </div>
      <div className="auth-showcase-copy">
        <span className="auth-kicker">
          Production engineering for AI agents
        </span>
        <h2>
          Ship reliable <span>AI agents.</span>
        </h2>
        <p>Observe, evaluate, diagnose, and ship with confidence.</p>
        <div className="auth-sequence">
          OBSERVE <b>·</b> EVALUATE <b>·</b> DIAGNOSE <b>·</b> SHIP
        </div>
      </div>
    </aside>
  );
}

export function MobileHealthPreview() {
  return (
    <div
      className="auth-mobile-preview"
      aria-label="Illustrative production health preview"
    >
      <div>
        <Activity size={16} />
        <span>Production Health</span>
        <small>Preview</small>
      </div>
      <div className="auth-mobile-metrics" aria-hidden="true">
        <span>
          <strong>11 / 13</strong> agents healthy
        </span>
        <span>
          <strong>98.2%</strong> success
        </span>
        <span>
          <strong>2</strong> incidents
        </span>
      </div>
      <span className="auth-mobile-flow">
        Observe <b>→</b> Diagnose <b>→</b> Ship
      </span>
    </div>
  );
}
