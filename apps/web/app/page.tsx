"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  DatasetPanel,
  EvidencePanel,
  type DatasetItemRecord,
  type DatasetRecord,
  type EvidenceBundle,
} from "./inspector-panels";
import { SpanInspector, type InspectedSpan } from "./span-inspector";
import { usePanelFocus } from "./use-panel-focus";
import { AuthVisual, MobileHealthPreview } from "./auth-visual";
import { BrandIdentity, BrandMark } from "./brand";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  ClipboardList,
  Database,
  Fingerprint,
  GitBranch,
  KeyRound,
  Layers3,
  LogOut,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  SlidersHorizontal,
  Workflow,
  X,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_CONTROL_API || "http://localhost:8000";
type RecordValue = Record<string, unknown>;
type Project = { id: string; name: string; slug: string };
type Trace = {
  trace_id: string;
  agent_name: string;
  root_name: string;
  start_time: string;
  duration_ms: number;
  span_count: number;
  error_count: number;
  cost_nano_usd: number;
  status: string;
  session_id: string;
};
type Span = InspectedSpan & {
  parent_span_id: string;
};
type TraceDetail = {
  trace_id: string;
  spans: Span[];
  graph: RecordValue | null;
  features: RecordValue | null;
};
type AgentHealth = {
  agent_name: string;
  runs: number;
  failed_runs: number;
  p95_latency_ms: number;
  cost_nano_usd: number;
  health: string;
  last_seen: string;
};
type Health = {
  window_hours: number;
  agents: AgentHealth[];
  open_incidents: number;
};
type Cluster = {
  signature: string;
  count: number;
  first_seen: string;
  last_seen: string;
  features: RecordValue;
  representatives: { trace_id: string; run_id: string }[];
};
type Incident = {
  id: string;
  title: string;
  severity: string;
  status: string;
  affected_runs: number;
  created_at: string;
  evidence_json?: RecordValue;
  cluster_signature: string;
};
type RegressionCandidate = {
  name: string;
  source_trace_id: string;
  cluster_signature: string | null;
  input: RecordValue;
  expect: RecordValue;
  review_required: boolean;
  evidence?: RecordValue;
};
type RegressionReview = {
  candidate: RegressionCandidate;
  name: string;
  input: string;
  expect: string;
  loading: boolean;
  notice: string;
  error: string;
  saving: boolean;
};
type Page =
  | "health"
  | "traces"
  | "sessions"
  | "clusters"
  | "incidents"
  | "regressions"
  | "datasets"
  | "release"
  | "changes"
  | "slos"
  | "keys";

const pagePath: Record<Page, string> = {
  health: "health",
  traces: "traces",
  sessions: "sessions",
  clusters: "clusters",
  incidents: "incidents",
  regressions: "regressions",
  datasets: "datasets",
  release: "release-evidence",
  changes: "changes",
  slos: "slos",
  keys: "keys",
};

const navigation: {
  label: string;
  items: { id: Page; label: string; icon: typeof Activity }[];
}[] = [
  {
    label: "PRODUCTION",
    items: [
      { id: "health", label: "Health", icon: Activity },
      { id: "traces", label: "Traces", icon: Workflow },
      { id: "sessions", label: "Sessions", icon: Layers3 },
    ],
  },
  {
    label: "DIAGNOSE",
    items: [
      { id: "clusters", label: "Failure clusters", icon: Fingerprint },
      { id: "incidents", label: "Incidents", icon: ShieldAlert },
      { id: "changes", label: "Change ledger", icon: GitBranch },
    ],
  },
  {
    label: "IMPROVE",
    items: [
      { id: "regressions", label: "Regression cases", icon: ClipboardList },
      { id: "datasets", label: "Datasets", icon: Database },
      { id: "release", label: "Release evidence", icon: Check },
    ],
  },
  {
    label: "SETTINGS",
    items: [
      { id: "slos", label: "SLO policies", icon: SlidersHorizontal },
      { id: "keys", label: "API keys", icon: KeyRound },
    ],
  },
];

let csrfPromise: Promise<string> | null = null;

function browserCsrfToken(): Promise<string> {
  if (!csrfPromise) {
    csrfPromise = fetch(`${API}/api/session/csrf`, {
      credentials: "include",
      cache: "no-store",
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("Browser session expired");
        const data = (await response.json()) as { token: string };
        return data.token;
      })
      .catch((error: unknown) => {
        csrfPromise = null;
        throw error;
      });
  }
  return csrfPromise;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method || "GET").toUpperCase();
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  if (
    !["GET", "HEAD", "OPTIONS"].includes(method) &&
    path !== "/api/login" &&
    path !== "/api/setup"
  ) {
    headers.set("X-CSRF-Token", await browserCsrfToken());
  }
  const response = await fetch(`${API}${path}`, {
    ...init,
    credentials: "include",
    headers,
  });
  if (!response.ok) {
    if (response.status === 403) csrfPromise = null;
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = typeof body.detail === "string" ? body.detail : message;
    } catch {
      /* no JSON body */
    }
    throw new Error(message);
  }
  if (["/api/login", "/api/setup", "/api/logout"].includes(path)) {
    csrfPromise = null;
  }
  return response.json() as Promise<T>;
}

function date(value: string | undefined) {
  return value ? new Date(value).toLocaleString() : "—";
}
function usd(nano: number | undefined) {
  return `$${((nano || 0) / 1_000_000_000).toFixed(4)}`;
}
function short(id: string | undefined, length = 10) {
  return id ? `${id.slice(0, length)}…` : "—";
}

function Badge({ value }: { value: string }) {
  return (
    <span
      className={`badge badge-${value.toLowerCase().replace(/[^a-z]+/g, "-")}`}
    >
      {value.replaceAll("_", " ")}
    </span>
  );
}

function Empty({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <CircleHelp size={28} strokeWidth={1.6} />
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}

function SectionHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="section-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}

function Auth({
  configured,
  onAuthenticated,
}: {
  configured: boolean;
  onAuthenticated: () => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [projectName, setProjectName] = useState("Production");
  const [bootstrap, setBootstrap] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await request(configured ? "/api/login" : "/api/setup", {
        method: "POST",
        headers: configured ? {} : { "X-Bootstrap-Token": bootstrap },
        body: JSON.stringify(
          configured
            ? { email, password }
            : { email, password, project_name: projectName },
        ),
      });
      onAuthenticated();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-wrap">
      <header className="auth-brand">
        <BrandIdentity />
      </header>
      <div className="auth-stage">
        <main className="auth-main">
          <div className="auth-card">
            <span className="auth-kicker">CONTROL SURFACE WORKSPACE</span>
            <h1>{configured ? "Welcome back" : "Set up your control plane"}</h1>
            <p>
              {configured
                ? "Sign in to your ControlSurface workspace."
                : "Create the first owner and project. Your bootstrap token is in the local .env file."}
            </p>
            <form onSubmit={submit}>
              <label>
                Email
                <input
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                />
              </label>
              <label>
                Password
                <input
                  type="password"
                  required
                  minLength={configured ? 1 : 12}
                  autoComplete={
                    configured ? "current-password" : "new-password"
                  }
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </label>
              {!configured && (
                <>
                  <label>
                    Project name
                    <input
                      required
                      value={projectName}
                      onChange={(e) => setProjectName(e.target.value)}
                    />
                  </label>
                  <label>
                    Bootstrap token
                    <input
                      required
                      type="password"
                      value={bootstrap}
                      onChange={(e) => setBootstrap(e.target.value)}
                    />
                  </label>
                </>
              )}
              {error && (
                <div className="form-error" role="alert">
                  {error}
                </div>
              )}
              <button className="button primary full" disabled={busy}>
                {busy ? "Working…" : configured ? "Sign in" : "Create owner"}
                <ArrowRight size={16} />
              </button>
            </form>
            <div className="auth-card-footer">
              <span className="auth-secure-dot" /> Self-hosted · Private by
              default
            </div>
          </div>
          <MobileHealthPreview />
        </main>
        <AuthVisual />
      </div>
    </div>
  );
}

function SpanTree({
  detail,
  onClose,
  onCreateRegression,
}: {
  detail: TraceDetail;
  onClose: () => void;
  onCreateRegression: (trace: TraceDetail) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const { closeRef, panelRef } = usePanelFocus(onClose);
  const byParent = useMemo(() => {
    const map = new Map<string, Span[]>();
    detail.spans.forEach((span) =>
      map.set(span.parent_span_id || "root", [
        ...(map.get(span.parent_span_id || "root") || []),
        span,
      ]),
    );
    for (const children of map.values()) {
      children.sort((left, right) => left.start_ns - right.start_ns);
    }
    return map;
  }, [detail.spans]);
  const current =
    detail.spans.find((span) => span.span_id === selected) || detail.spans[0];
  const visited = new Set<string>();
  function renderSpan(span: Span, depth: number): React.ReactNode {
    if (visited.has(span.span_id)) return null;
    visited.add(span.span_id);
    return (
      <div key={span.span_id}>
        <button
          className={`span-row ${current?.span_id === span.span_id ? "selected" : ""}`}
          style={{ paddingLeft: 14 + Math.min(depth, 20) * 20 }}
          onClick={() => {
            setSelected(span.span_id);
          }}
        >
          <span
            className={`span-dot ${span.status === "error" ? "error" : span.operation}`}
          />
          <span className="span-name">{span.name}</span>
          <span className="span-kind">{span.operation}</span>
          <span className="mono muted">
            {((span.end_ns - span.start_ns) / 1e6).toFixed(0)}ms
          </span>
        </button>
        {(byParent.get(span.span_id) || []).map((child) =>
          renderSpan(child, depth + 1),
        )}
      </div>
    );
  }
  const spanIds = new Set(detail.spans.map((span) => span.span_id));
  const roots = detail.spans.filter(
    (span) => !span.parent_span_id || !spanIds.has(span.parent_span_id),
  );
  roots.sort((left, right) => left.start_ns - right.start_ns);
  const rootRows = roots.map((span) => renderSpan(span, 0));
  const unlinkedRows = detail.spans
    .filter((span) => !visited.has(span.span_id))
    .sort((left, right) => left.start_ns - right.start_ns)
    .map((span) => renderSpan(span, 0));
  return (
    <div className="detail-overlay">
      <section
        className="detail-panel"
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="trace-title"
      >
        <div className="detail-top">
          <button
            ref={closeRef}
            className="icon-button"
            onClick={onClose}
            aria-label="Close trace"
          >
            <X size={18} />
          </button>
          <span className="eyebrow">TRACE {short(detail.trace_id, 16)}</span>
          <button
            className="button subtle"
            onClick={() => onCreateRegression(detail)}
          >
            Create regression <ArrowRight size={15} />
          </button>
        </div>
        <div className="detail-intro">
          <h2 id="trace-title">
            {roots[0]?.name || detail.spans[0]?.name || "Agent run"}
          </h2>
          <div className="detail-meta">
            <Badge
              value={
                detail.spans.some((s) => s.status === "error")
                  ? "error"
                  : "success"
              }
            />
            <span>{detail.spans.length} spans</span>
            <span>
              {usd(detail.spans.reduce((sum, s) => sum + s.cost_nano_usd, 0))}
            </span>
          </div>
        </div>
        <div className="trace-layout">
          <div className="trace-tree">
            <div className="pane-label">EXECUTION</div>
            {rootRows}
            {unlinkedRows.length > 0 && (
              <div className="pane-label unlinked-label">
                UNLINKED OR CYCLIC SPANS
              </div>
            )}
            {unlinkedRows}
          </div>
          <div className="span-detail">
            <div className="pane-label">SPAN DETAIL</div>
            {current && <SpanInspector key={current.span_id} span={current} />}
          </div>
        </div>
      </section>
    </div>
  );
}

export default function Home() {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [page, setPage] = useState<Page>("health");
  const [resource, setResource] = useState<{
    projectId: string;
    page: Page;
    value: unknown;
  } | null>(null);
  const [detail, setDetail] = useState<TraceDetail | null>(null);
  const [regressionReview, setRegressionReview] =
    useState<RegressionReview | null>(null);
  const [incident, setIncident] = useState<Incident | null>(null);
  const [dataset, setDataset] = useState<DatasetRecord | null>(null);
  const [releaseEvidence, setReleaseEvidence] = useState<EvidenceBundle | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [keyOnce, setKeyOnce] = useState("");
  const [form, setForm] = useState("");
  const data =
    resource?.projectId === projectId && resource.page === page
      ? resource.value
      : null;

  const refreshIdentity = useCallback(async () => {
    try {
      const status = await request<{ configured: boolean }>(
        "/api/setup/status",
      );
      setConfigured(status.configured);
      if (!status.configured) return;
      const list = await request<Project[]>("/api/projects");
      setProjects(list);
      setProjectId((old) =>
        list.some((p) => p.id === old) ? old : list[0]?.id || "",
      );
    } catch (e) {
      setError((e as Error).message);
      setConfigured(true);
    }
  }, []);
  useEffect(() => {
    void refreshIdentity();
  }, [refreshIdentity]);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    setResource(null);
    try {
      const value = await request(
        `/api/projects/${projectId}/${pagePath[page]}`,
      );
      setResource({ projectId, page, value });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [projectId, page]);
  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function openTrace(id: string) {
    try {
      setDetail(
        await request<TraceDetail>(`/api/projects/${projectId}/traces/${id}`),
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function openIncident(id: string) {
    try {
      setIncident(
        await request<Incident>(`/api/projects/${projectId}/incidents/${id}`),
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const loadDatasetItems = useCallback(
    (datasetId: string) =>
      request<DatasetItemRecord[]>(
        `/api/projects/${projectId}/datasets/${datasetId}/items`,
      ),
    [projectId],
  );
  const saveDatasetItem = useCallback(
    async (datasetId: string, input: RecordValue, expected: RecordValue) => {
      await request(`/api/projects/${projectId}/datasets/${datasetId}/items`, {
        method: "POST",
        body: JSON.stringify({ input, expected }),
      });
    },
    [projectId],
  );
  async function openReleaseEvidence(id: string) {
    try {
      setReleaseEvidence(
        await request<EvidenceBundle>(
          `/api/projects/${projectId}/release-evidence/${id}`,
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function submit(pathPart: string, body: RecordValue) {
    try {
      await request(`/api/projects/${projectId}/${pathPart}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setForm("");
      void refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function analyze(signature: string) {
    await submit("incidents/analyze", {
      cluster_signature: signature,
      severity: "medium",
    });
    setPage("incidents");
  }
  async function createRegression(trace: TraceDetail) {
    const signature = trace.features?.failure_signature;
    const clusterSignature =
      typeof signature === "string" && /^[a-f0-9]{24}$/.test(signature)
        ? signature
        : null;
    const raw = trace.spans.find(
      (span) => "controlsurface.input" in span.attributes,
    )?.attributes["controlsurface.input"];
    let parsed = raw;
    if (typeof raw === "string") {
      try {
        parsed = JSON.parse(raw);
      } catch {
        parsed = raw;
      }
    }
    const input =
      parsed && typeof parsed === "object" && !Array.isArray(parsed)
        ? (parsed as RecordValue)
        : parsed == null
          ? {}
          : { message: parsed };
    const fallback: RegressionCandidate = {
      name: "Production failure " + trace.trace_id.slice(0, 8),
      source_trace_id: trace.trace_id,
      cluster_signature: clusterSignature,
      input,
      expect: { completion: true },
      review_required: true,
    };
    setRegressionReview({
      candidate: fallback,
      name: fallback.name,
      input: JSON.stringify(input, null, 2),
      expect: JSON.stringify(fallback.expect, null, 2),
      loading: !!clusterSignature,
      notice: clusterSignature
        ? ""
        : "No failure cluster is linked to this trace. Review the extracted input before saving.",
      error: "",
      saving: false,
    });
    if (!clusterSignature) return;
    try {
      const candidates = await request<RegressionCandidate[]>(
        "/api/projects/" +
          projectId +
          "/regressions/candidates?cluster_signature=" +
          clusterSignature,
      );
      const mined = candidates.find(
        (candidate) => candidate.source_trace_id === trace.trace_id,
      );
      setRegressionReview((current) =>
        current?.candidate.source_trace_id === trace.trace_id
          ? mined
            ? {
                ...current,
                candidate: mined,
                name: mined.name,
                input: JSON.stringify(mined.input, null, 2),
                expect: JSON.stringify(mined.expect, null, 2),
                loading: false,
              }
            : {
                ...current,
                loading: false,
                notice:
                  "This trace is not a representative case for its cluster. Review the extracted input before saving.",
              }
          : current,
      );
    } catch (e) {
      setRegressionReview((current) =>
        current?.candidate.source_trace_id === trace.trace_id
          ? {
              ...current,
              loading: false,
              notice:
                "Could not load a mined candidate: " +
                (e as Error).message +
                ". Review this trace manually.",
            }
          : current,
      );
    }
  }
  async function saveRegression(event: React.FormEvent) {
    event.preventDefault();
    if (
      !regressionReview ||
      regressionReview.loading ||
      regressionReview.saving
    )
      return;
    const name = regressionReview.name.trim();
    if (!name) {
      setRegressionReview(
        (current) => current && { ...current, error: "Give this case a name." },
      );
      return;
    }
    let input: unknown;
    let expect: unknown;
    try {
      input = JSON.parse(regressionReview.input);
      expect = JSON.parse(regressionReview.expect);
    } catch {
      setRegressionReview(
        (current) =>
          current && {
            ...current,
            error: "Input and expected result must be valid JSON.",
          },
      );
      return;
    }
    if (
      !input ||
      typeof input !== "object" ||
      Array.isArray(input) ||
      !expect ||
      typeof expect !== "object" ||
      Array.isArray(expect)
    ) {
      setRegressionReview(
        (current) =>
          current && {
            ...current,
            error: "Input and expected result must each be a JSON object.",
          },
      );
      return;
    }
    setRegressionReview(
      (current) => current && { ...current, saving: true, error: "" },
    );
    try {
      await request("/api/projects/" + projectId + "/regressions", {
        method: "POST",
        body: JSON.stringify({
          name,
          source_trace_id: regressionReview.candidate.source_trace_id,
          cluster_signature: regressionReview.candidate.cluster_signature,
          input,
          expect,
        }),
      });
      setRegressionReview(null);
      setDetail(null);
      setPage("regressions");
      if (page === "regressions") void refresh();
    } catch (e) {
      setRegressionReview(
        (current) =>
          current && { ...current, saving: false, error: (e as Error).message },
      );
    }
  }
  async function createKey() {
    const label = window.prompt("API key label", "Local SDK");
    if (!label) return;
    try {
      const result = await request<{ key: string }>(
        `/api/projects/${projectId}/keys`,
        { method: "POST", body: JSON.stringify({ label }) },
      );
      setKeyOnce(result.key);
      void refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function logout() {
    await request("/api/logout", { method: "POST" });
    setProjects([]);
    setProjectId("");
    setConfigured(true);
  }

  if (configured === null)
    return (
      <div className="boot">
        <BrandMark />
        <span>Connecting to ControlSurface…</span>
      </div>
    );
  if (!projects.length)
    return <Auth configured={configured} onAuthenticated={refreshIdentity} />;
  const project = projects.find((p) => p.id === projectId);
  const title =
    navigation.flatMap((group) => group.items).find((item) => item.id === page)
      ?.label || page;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <BrandMark />
          <div>
            <strong>ControlSurface</strong>
            <small>Production engineering</small>
          </div>
        </div>
        <div className="project-select">
          <span className="project-avatar">
            {project?.name.charAt(0).toUpperCase()}
          </span>
          <select
            aria-label="Project"
            value={projectId}
            onChange={(e) => {
              setProjectId(e.target.value);
              setDataset(null);
              setReleaseEvidence(null);
              setDetail(null);
              setIncident(null);
            }}
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <ChevronDown size={14} />
        </div>
        <nav aria-label="Main navigation">
          {navigation.map((group) => (
            <div className="nav-group" key={group.label}>
              <div className="nav-label">{group.label}</div>
              {group.items.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    className={`nav-link ${page === item.id ? "active" : ""}`}
                    aria-current={page === item.id ? "page" : undefined}
                    onClick={() => {
                      setPage(item.id);
                      setDetail(null);
                      setIncident(null);
                      setForm("");
                    }}
                  >
                    <Icon size={17} strokeWidth={1.8} />
                    {item.label}
                    {page === item.id && (
                      <ChevronRight size={14} className="nav-chevron" />
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="env-dot" /> Self-hosted V1{" "}
          <button onClick={logout} title="Sign out" aria-label="Sign out">
            <LogOut size={17} />
          </button>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div className="breadcrumb">
            {project?.name}
            <ChevronRight size={14} />
            {title}
          </div>
          <div className="top-actions">
            <span className="live-indicator">
              <span />
              Observed data
            </span>
            <button
              className="icon-button"
              aria-label="Refresh"
              title="Refresh"
              onClick={() => void refresh()}
            >
              <RefreshCw size={16} />
            </button>
          </div>
        </header>
        <div className="content">
          {error && (
            <div className="error-banner" role="alert">
              <AlertTriangle size={17} />
              {error}
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {page === "health" && (
            <>
              <SectionHeading
                eyebrow="PRODUCTION / LAST 24 HOURS"
                title="Production Health"
                description="Your agents' operational status, grounded in observed runs."
                action={
                  <button
                    className="button subtle"
                    onClick={() => setPage("incidents")}
                  >
                    View incidents <ArrowRight size={15} />
                  </button>
                }
              />
              {loading ? (
                <div className="skeleton-row" />
              ) : (
                (() => {
                  const health = data as Health | null;
                  const agents = health?.agents || [];
                  return (
                    <>
                      <div className="metric-strip">
                        <div>
                          <span>Observed agents</span>
                          <strong>{agents.length}</strong>
                          <small>Last 24 hours</small>
                        </div>
                        <div>
                          <span>Healthy</span>
                          <strong>
                            {
                              agents.filter((a) => a.health === "healthy")
                                .length
                            }
                          </strong>
                          <small>With passing SLO</small>
                        </div>
                        <div>
                          <span>Degraded</span>
                          <strong>
                            {
                              agents.filter((a) => a.health === "degraded")
                                .length
                            }
                          </strong>
                          <small>Active policy breaches</small>
                        </div>
                        <div>
                          <span>Open incidents</span>
                          <strong>{health?.open_incidents ?? 0}</strong>
                          <small>Needs investigation</small>
                        </div>
                      </div>
                      <div className="panel">
                        <div className="panel-heading">
                          <div>
                            <h2>Agent status</h2>
                            <p>
                              Measured from real traces; configure an SLO to
                              classify health.
                            </p>
                          </div>
                          <span className="panel-count">
                            {agents.length} agents
                          </span>
                        </div>
                        {agents.length ? (
                          <table>
                            <thead>
                              <tr>
                                <th>Agent</th>
                                <th>State</th>
                                <th>Runs</th>
                                <th>Failures</th>
                                <th>P95 latency</th>
                                <th>Cost</th>
                                <th>Last seen</th>
                              </tr>
                            </thead>
                            <tbody>
                              {agents.map((agent) => (
                                <tr key={agent.agent_name}>
                                  <td className="strong">
                                    {agent.agent_name || "Unnamed agent"}
                                  </td>
                                  <td>
                                    <Badge value={agent.health} />
                                  </td>
                                  <td>{agent.runs}</td>
                                  <td>{agent.failed_runs}</td>
                                  <td>{agent.p95_latency_ms} ms</td>
                                  <td>{usd(agent.cost_nano_usd)}</td>
                                  <td>{date(agent.last_seen)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        ) : (
                          <Empty
                            title="No agent runs yet"
                            description="Create an API key, instrument the Python example and run it to populate production health."
                            action={
                              <button
                                className="button subtle"
                                onClick={() => setPage("keys")}
                              >
                                Set up an API key <ArrowRight size={15} />
                              </button>
                            }
                          />
                        )}
                      </div>
                    </>
                  );
                })()
              )}
            </>
          )}
          {page === "traces" && (
            <>
              <SectionHeading
                eyebrow="OBSERVE / EXECUTION"
                title="Traces"
                description="Inspect every model call, tool, retrieval and agent step."
                action={
                  <button
                    className="button subtle"
                    onClick={() => void refresh()}
                  >
                    <RefreshCw size={15} /> Refresh
                  </button>
                }
              />
              <div className="toolbar">
                <Search size={17} />
                <input
                  aria-label="Filter traces"
                  placeholder="Filter by agent or trace ID"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                <span>Latest 50</span>
              </div>
              <div className="panel table-panel">
                {loading ? (
                  <div className="skeleton-row" />
                ) : (
                  (() => {
                    const traces = ((data as Trace[] | null) || []).filter(
                      (t) =>
                        `${t.agent_name} ${t.trace_id}`
                          .toLowerCase()
                          .includes(search.toLowerCase()),
                    );
                    return traces.length ? (
                      <table>
                        <thead>
                          <tr>
                            <th>Run</th>
                            <th>State</th>
                            <th>Agent</th>
                            <th>Spans</th>
                            <th>Duration</th>
                            <th>Cost</th>
                            <th>Started</th>
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {traces.map((trace) => (
                            <tr key={trace.trace_id}>
                              <td>
                                <button
                                  className="text-button row-link strong"
                                  onClick={() => void openTrace(trace.trace_id)}
                                >
                                  {trace.root_name}
                                </button>
                                <span className="mono muted">
                                  {short(trace.trace_id, 12)}
                                </span>
                              </td>
                              <td>
                                <Badge value={trace.status} />
                              </td>
                              <td>{trace.agent_name || "—"}</td>
                              <td>{trace.span_count}</td>
                              <td>{trace.duration_ms} ms</td>
                              <td>{usd(trace.cost_nano_usd)}</td>
                              <td>{date(trace.start_time)}</td>
                              <td>
                                <ChevronRight size={16} />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <Empty
                        title="No traces found"
                        description="Telemetry appears here after the SDK sends an agent run and the worker processes it."
                      />
                    );
                  })()
                )}
              </div>
            </>
          )}
          {page === "sessions" && (
            <>
              <SectionHeading
                eyebrow="OBSERVE / CONTEXT"
                title="Sessions"
                description="Runs grouped by application session identity."
              />
              <div className="panel table-panel">
                {loading ? (
                  <div className="skeleton-row" />
                ) : (data as RecordValue[] | null)?.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Session</th>
                        <th>Traces</th>
                        <th>Errors</th>
                        <th>Cost</th>
                        <th>Last seen</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data as RecordValue[]).map((s, i) => (
                        <tr key={i}>
                          <td className="mono">
                            {short(String(s.session_id), 24)}
                          </td>
                          <td>{String(s.trace_count)}</td>
                          <td>{String(s.errors)}</td>
                          <td>{usd(Number(s.cost_nano_usd))}</td>
                          <td>{date(String(s.last_seen))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <Empty
                    title="No sessions yet"
                    description="Set a session ID in the Python SDK to connect related agent runs."
                  />
                )}
              </div>
            </>
          )}
          {page === "clusters" && (
            <>
              <SectionHeading
                eyebrow="DIAGNOSE / PATTERNS"
                title="Failure clusters"
                description="Deterministic grouping by execution structure, tool sequence and error evidence."
              />
              <div className="stack">
                {loading ? (
                  <div className="skeleton-row" />
                ) : (data as Cluster[] | null)?.length ? (
                  (data as Cluster[]).map((cluster) => (
                    <div className="panel cluster" key={cluster.signature}>
                      <div className="cluster-top">
                        <div>
                          <span className="eyebrow">
                            SIGNATURE {short(cluster.signature, 12)}
                          </span>
                          <h2>
                            {String(
                              cluster.features.failed_tool ||
                                cluster.features.error_type ||
                                "Agent execution failure",
                            )}
                          </h2>
                          <p>
                            {cluster.count} affected runs · First seen{" "}
                            {date(cluster.first_seen)}
                          </p>
                        </div>
                        <div className="cluster-actions">
                          <span className="count-pill">
                            {cluster.count} runs
                          </span>
                          <button
                            className="button primary"
                            onClick={() => void analyze(cluster.signature)}
                          >
                            Create incident <ArrowRight size={15} />
                          </button>
                        </div>
                      </div>
                      <div className="cluster-evidence">
                        <span>
                          Tool sequence:{" "}
                          {Array.isArray(cluster.features.tool_sequence)
                            ? cluster.features.tool_sequence.join(" → ") ||
                              "none"
                            : "none"}
                        </span>
                        <span>
                          Retries: {String(cluster.features.retry_count || 0)}
                        </span>
                        <span>
                          Representatives: {cluster.representatives.length}
                        </span>
                      </div>
                      <div className="representatives">
                        {cluster.representatives.map((r) => (
                          <button
                            key={r.trace_id}
                            onClick={() => void openTrace(r.trace_id)}
                          >
                            Representative run{" "}
                            <span className="mono">{short(r.trace_id)}</span>
                            <ChevronRight size={15} />
                          </button>
                        ))}
                      </div>
                    </div>
                  ))
                ) : (
                  <Empty
                    title="No failures to cluster"
                    description="Failed agent runs will be grouped here as telemetry arrives."
                  />
                )}
              </div>
            </>
          )}
          {page === "incidents" && (
            <>
              <SectionHeading
                eyebrow="DIAGNOSE / RESPONSE"
                title="Incidents"
                description="Failure evidence and ranked change correlations, with limits stated clearly."
              />
              <div className="panel table-panel">
                {loading ? (
                  <div className="skeleton-row" />
                ) : (data as Incident[] | null)?.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Incident</th>
                        <th>Severity</th>
                        <th>Status</th>
                        <th>Affected runs</th>
                        <th>Created</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {(data as Incident[]).map((item) => (
                        <tr key={item.id}>
                          <td>
                            <button
                              className="text-button row-link strong"
                              onClick={() => void openIncident(item.id)}
                            >
                              {item.title}
                            </button>
                            <span className="mono muted">{short(item.id)}</span>
                          </td>
                          <td>
                            <Badge value={item.severity} />
                          </td>
                          <td>
                            <Badge value={item.status} />
                          </td>
                          <td>{item.affected_runs}</td>
                          <td>{date(item.created_at)}</td>
                          <td>
                            <ChevronRight size={16} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <Empty
                    title="No incidents"
                    description="Inspect a failure cluster and create an incident with ranked, inspectable change evidence."
                    action={
                      <button
                        className="button subtle"
                        onClick={() => setPage("clusters")}
                      >
                        Explore clusters <ArrowRight size={15} />
                      </button>
                    }
                  />
                )}
              </div>
            </>
          )}
          {page === "changes" && (
            <>
              <SectionHeading
                eyebrow="DIAGNOSE / HISTORY"
                title="Change ledger"
                description="Versioned changes that incident analysis can correlate with failures."
                action={
                  <button
                    className="button primary"
                    onClick={() => setForm("change")}
                  >
                    <Plus size={16} /> Record change
                  </button>
                }
              />
              <div className="panel table-panel">
                {loading ? (
                  <div className="skeleton-row" />
                ) : (data as RecordValue[] | null)?.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Change</th>
                        <th>Subject</th>
                        <th>Version</th>
                        <th>Environment</th>
                        <th>Effective</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data as RecordValue[]).map((c, i) => (
                        <tr key={i}>
                          <td>
                            <Badge value={String(c.change_type)} />
                          </td>
                          <td className="strong">{String(c.subject_name)}</td>
                          <td className="mono">
                            {String(c.before_version || "—")} →{" "}
                            {String(c.after_version || "—")}
                          </td>
                          <td>{String(c.environment)}</td>
                          <td>{date(String(c.effective_at))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <Empty
                    title="No changes recorded"
                    description="Record deployments, tool schemas, prompts and model changes so incidents have explicit evidence."
                  />
                )}
              </div>
            </>
          )}
          {page === "regressions" && (
            <>
              <SectionHeading
                eyebrow="IMPROVE / MEMORY"
                title="Regression cases"
                description="Reviewed production failures become permanent, reusable checks."
              />
              <div className="panel table-panel">
                {loading ? (
                  <div className="skeleton-row" />
                ) : (data as RecordValue[] | null)?.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Case</th>
                        <th>Source trace</th>
                        <th>Cluster</th>
                        <th>Revision</th>
                        <th>Created</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data as RecordValue[]).map((c, i) => (
                        <tr key={i}>
                          <td className="strong">{String(c.name)}</td>
                          <td>
                            <button
                              className="text-button mono"
                              onClick={() =>
                                void openTrace(String(c.source_trace_id))
                              }
                            >
                              {short(String(c.source_trace_id))}
                            </button>
                          </td>
                          <td className="mono muted">
                            {short(String(c.cluster_signature || ""))}
                          </td>
                          <td className="mono muted">
                            {short(String(c.revision))}
                          </td>
                          <td>{date(String(c.created_at))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <Empty
                    title="No regression cases"
                    description="Open a failed trace, review its input and expected outcome, then save it as a regression case."
                    action={
                      <button
                        className="button subtle"
                        onClick={() => setPage("clusters")}
                      >
                        Explore failures <ArrowRight size={15} />
                      </button>
                    }
                  />
                )}
              </div>
            </>
          )}
          {page === "datasets" && (
            <>
              <SectionHeading
                eyebrow="EVALUATE / INPUTS"
                title="Datasets"
                description="Versioned scenario collections for local evaluations."
                action={
                  <button
                    className="button primary"
                    onClick={() => setForm("dataset")}
                  >
                    <Plus size={16} /> New dataset
                  </button>
                }
              />
              <div className="panel table-panel">
                {loading ? (
                  <div className="skeleton-row" />
                ) : (data as RecordValue[] | null)?.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Dataset</th>
                        <th>Revision</th>
                        <th>Created</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data as RecordValue[]).map((d) => (
                        <tr key={String(d.id)}>
                          <td>
                            <button
                              className="text-button row-link strong"
                              onClick={() => setDataset(d as DatasetRecord)}
                            >
                              {String(d.name)}
                            </button>
                          </td>
                          <td className="mono">r{String(d.revision)}</td>
                          <td>{date(String(d.created_at))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <Empty
                    title="No datasets"
                    description="Create a dataset to collect evaluation scenarios and expected results."
                  />
                )}
              </div>
            </>
          )}
          {page === "release" && (
            <>
              <SectionHeading
                eyebrow="SHIP / DECISIONS"
                title="Release evidence"
                description="Frozen gate inputs, results and reasons produced by the CLI."
              />
              <div className="panel table-panel">
                {loading ? (
                  <div className="skeleton-row" />
                ) : (data as RecordValue[] | null)?.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Decision</th>
                        <th>Candidate</th>
                        <th>Reasons</th>
                        <th>Evidence hash</th>
                        <th>Created</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data as RecordValue[]).map((item) => {
                        const decision = item.decision as RecordValue;
                        const manifest = item.manifest as RecordValue;
                        return (
                          <tr key={String(item.id)}>
                            <td>
                              <Badge
                                value={decision.passed ? "passed" : "blocked"}
                              />
                            </td>
                            <td>
                              <button
                                className="text-button row-link strong"
                                onClick={() =>
                                  void openReleaseEvidence(String(item.id))
                                }
                              >
                                {String(manifest.candidate_version)}
                              </button>
                            </td>
                            <td>
                              {Array.isArray(decision.reasons)
                                ? decision.reasons.join(", ") || "No violations"
                                : "—"}
                            </td>
                            <td className="mono muted">
                              {short(String(item.evidence_sha256), 16)}
                            </td>
                            <td>{date(String(item.created_at))}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                ) : (
                  <Empty
                    title="No release decisions"
                    description="Run controlsurface gate against paired local evaluation results to create immutable evidence."
                  />
                )}
              </div>
            </>
          )}
          {page === "slos" && (
            <>
              <SectionHeading
                eyebrow="SETTINGS / RELIABILITY"
                title="SLO policies"
                description="Per-agent thresholds determine whether production health is healthy or degraded."
                action={
                  <button
                    className="button primary"
                    onClick={() => setForm("slo")}
                  >
                    <Plus size={16} /> Add policy
                  </button>
                }
              />
              <div className="panel table-panel">
                {loading ? (
                  <div className="skeleton-row" />
                ) : (data as RecordValue[] | null)?.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Agent</th>
                        <th>Completion min</th>
                        <th>Tool success min</th>
                        <th>P95 max</th>
                        <th>Min samples</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data as RecordValue[]).map((s, i) => {
                        const p = s.policy_json as RecordValue;
                        return (
                          <tr key={i}>
                            <td className="strong">{String(s.agent_name)}</td>
                            <td>
                              {(Number(p.completion_rate_min) * 100).toFixed(1)}
                              %
                            </td>
                            <td>
                              {(Number(p.tool_success_rate_min) * 100).toFixed(
                                1,
                              )}
                              %
                            </td>
                            <td>{String(p.p95_latency_ms_max)} ms</td>
                            <td>{String(p.minimum_samples)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                ) : (
                  <Empty
                    title="No SLO policies"
                    description="Define agent reliability targets to classify real production health."
                  />
                )}
              </div>
            </>
          )}
          {page === "keys" && (
            <>
              <SectionHeading
                eyebrow="SETTINGS / ACCESS"
                title="API keys"
                description="Project-scoped ingestion credentials. Raw keys are shown only once."
                action={
                  <button
                    className="button primary"
                    onClick={() => void createKey()}
                  >
                    <Plus size={16} /> Create key
                  </button>
                }
              />
              {keyOnce && (
                <div className="key-reveal">
                  <div>
                    <strong>Copy this key now</strong>
                    <p>It will not be shown again.</p>
                    <code>{keyOnce}</code>
                  </div>
                  <button
                    className="icon-button"
                    onClick={() => setKeyOnce("")}
                    aria-label="Dismiss key"
                  >
                    <X size={17} />
                  </button>
                </div>
              )}
              <div className="panel table-panel">
                {loading ? (
                  <div className="skeleton-row" />
                ) : (data as RecordValue[] | null)?.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Label</th>
                        <th>Prefix</th>
                        <th>Created</th>
                        <th>Status</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {(data as RecordValue[]).map((k, i) => (
                        <tr key={i}>
                          <td className="strong">{String(k.label)}</td>
                          <td className="mono">{String(k.prefix)}…</td>
                          <td>{date(String(k.created_at))}</td>
                          <td>
                            <Badge
                              value={k.revoked_at ? "revoked" : "active"}
                            />
                          </td>
                          <td>
                            {!k.revoked_at && (
                              <button
                                className="text-button danger"
                                onClick={async () => {
                                  if (!window.confirm("Revoke this API key?"))
                                    return;
                                  try {
                                    await request(
                                      `/api/projects/${projectId}/keys/${String(k.id)}`,
                                      { method: "DELETE" },
                                    );
                                    void refresh();
                                  } catch (e) {
                                    setError((e as Error).message);
                                  }
                                }}
                              >
                                Revoke
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <Empty
                    title="No API keys"
                    description="Create a project-scoped key for the Python SDK and OTLP exporters."
                  />
                )}
              </div>
            </>
          )}
        </div>
      </main>
      {detail && (
        <SpanTree
          detail={detail}
          onClose={() => setDetail(null)}
          onCreateRegression={createRegression}
        />
      )}
      {dataset && (
        <DatasetPanel
          dataset={dataset}
          loadItems={loadDatasetItems}
          saveItem={saveDatasetItem}
          onSaved={() => void refresh()}
          onClose={() => setDataset(null)}
        />
      )}
      {releaseEvidence && (
        <EvidencePanel
          bundle={releaseEvidence}
          onClose={() => setReleaseEvidence(null)}
        />
      )}
      {incident && (
        <div className="detail-overlay">
          <div className="detail-panel incident-panel">
            <div className="detail-top">
              <button
                className="icon-button"
                onClick={() => setIncident(null)}
                aria-label="Close incident"
              >
                <X size={18} />
              </button>
              <span className="eyebrow">INCIDENT {short(incident.id)}</span>
            </div>
            <div className="detail-intro">
              <h2>{incident.title}</h2>
              <div className="detail-meta">
                <Badge value={incident.severity} />
                <Badge value={incident.status} />
                <span>{incident.affected_runs} affected runs</span>
              </div>
            </div>
            <div className="incident-content">
              <h3>Evidence-ranked change candidates</h3>
              <p className="muted">
                Associations are not causal proof. Inspect versions and
                representative runs before acting.
              </p>
              {(
                (incident.evidence_json?.root_cause_candidates ||
                  []) as RecordValue[]
              ).length ? (
                (
                  (incident.evidence_json?.root_cause_candidates ||
                    []) as RecordValue[]
                ).map((c, i) => (
                  <div className="candidate" key={i}>
                    <strong>{String(c.subject)}</strong>
                    <Badge value={String(c.change_type)} />
                    <span>Evidence score {String(c.evidence_score)}</span>
                    <p>
                      {String(c.before_version || "—")} →{" "}
                      {String(c.after_version || "—")} ·{" "}
                      {String(c.minutes_before_first_failure)} min before first
                      failure
                    </p>
                  </div>
                ))
              ) : (
                <Empty
                  title="No nearby changes"
                  description="No change events were recorded within the two-hour correlation window."
                />
              )}
              <h3>Representative runs</h3>
              {(
                ((incident.evidence_json?.cluster as RecordValue)
                  ?.representatives as RecordValue[]) || []
              ).map((r, i) => (
                <button
                  className="representative-link"
                  key={i}
                  onClick={() => {
                    setIncident(null);
                    void openTrace(String(r.trace_id));
                  }}
                >
                  {String(r.trace_id)} <ArrowRight size={15} />
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
      {regressionReview && (
        <div className="modal-backdrop">
          <RegressionModal
            review={regressionReview}
            onChange={(changes) =>
              setRegressionReview(
                (current) => current && { ...current, ...changes, error: "" },
              )
            }
            onClose={() => setRegressionReview(null)}
            onSubmit={saveRegression}
          />
        </div>
      )}
      {form && (
        <div className="modal-backdrop">
          <FormModal
            type={form}
            onClose={() => setForm("")}
            onSubmit={submit}
          />
        </div>
      )}
    </div>
  );
}

function RegressionModal({
  review,
  onChange,
  onClose,
  onSubmit,
}: {
  review: RegressionReview;
  onChange: (changes: Partial<RegressionReview>) => void;
  onClose: () => void;
  onSubmit: (event: React.FormEvent) => Promise<void>;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);
  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const dialog = dialogRef.current;
    dialog?.querySelector<HTMLInputElement>("input")?.focus();
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeRef.current();
      }
      if (event.key !== "Tab" || !dialog) return;
      const items = Array.from(
        dialog.querySelectorAll<HTMLElement>(
          "button:not([disabled]), input:not([disabled]), textarea:not([disabled])",
        ),
      );
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("keydown", handleKey);
      previous?.focus();
    };
  }, []);
  const evidence = review.candidate.evidence;
  return (
    <div
      className="modal regression-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="regression-review-title"
      ref={dialogRef}
    >
      <div className="modal-header">
        <div>
          <span className="eyebrow">PRODUCTION-DERIVED TEST</span>
          <h2 id="regression-review-title">Review regression case</h2>
        </div>
        <button
          type="button"
          className="icon-button"
          onClick={onClose}
          aria-label="Close regression review"
        >
          <X size={18} />
        </button>
      </div>
      <p className="regression-intro">
        Confirm the captured input and expected behavior. A production failure
        is evidence, not an automatic assertion.
      </p>
      <div className="regression-source">
        <span>
          Source trace{" "}
          <code>{short(review.candidate.source_trace_id, 16)}</code>
        </span>
        {evidence && (
          <span>{String(evidence.affected_runs ?? 1)} related failures</span>
        )}
      </div>
      {review.loading && (
        <div className="regression-notice" role="status">
          Loading representative case and failure evidence…
        </div>
      )}
      {review.notice && (
        <div className="regression-notice" role="status">
          {review.notice}
        </div>
      )}
      {evidence?.input_available === false && (
        <div className="regression-notice">
          The source run did not capture its input. Fill it in before saving.
        </div>
      )}
      <form onSubmit={onSubmit}>
        <label>
          Case name
          <input
            required
            maxLength={160}
            value={review.name}
            disabled={review.loading || review.saving}
            onChange={(event) => onChange({ name: event.target.value })}
          />
        </label>
        <label>
          Input JSON
          <textarea
            required
            spellCheck={false}
            rows={7}
            value={review.input}
            disabled={review.loading || review.saving}
            onChange={(event) => onChange({ input: event.target.value })}
          />
        </label>
        <label>
          Expected behavior JSON
          <textarea
            required
            spellCheck={false}
            rows={7}
            value={review.expect}
            disabled={review.loading || review.saving}
            onChange={(event) => onChange({ expect: event.target.value })}
          />
        </label>
        {review.error && (
          <div className="form-error" role="alert">
            {review.error}
          </div>
        )}
        <div className="modal-actions">
          <button type="button" className="button subtle" onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            className="button primary"
            disabled={review.loading || review.saving}
          >
            {review.saving ? "Saving…" : "Save regression"} <Check size={15} />
          </button>
        </div>
      </form>
    </div>
  );
}

function FormModal({
  type,
  onClose,
  onSubmit,
}: {
  type: string;
  onClose: () => void;
  onSubmit: (path: string, body: RecordValue) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("");
  const [before, setBefore] = useState("");
  const [after, setAfter] = useState("");
  const [error, setError] = useState("");
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    if (type === "dataset") await onSubmit("datasets", { name });
    else if (type === "slo")
      await onSubmit("slos", {
        agent_name: name,
        policy: {
          minimum_samples: 20,
          completion_rate_min: Number(before || 0.98),
          tool_success_rate_min: 0.99,
          p95_latency_ms_max: Number(after || 8000),
          average_cost_nano_usd_max: 80000000,
          maximum_steps_max: 12,
        },
      });
    else if (type === "change")
      await onSubmit("changes", {
        change_type: name,
        subject_type: "deployment",
        subject_name: subject,
        before_version: before || null,
        after_version: after || null,
        environment: "production",
        effective_at: new Date().toISOString(),
        details: {},
      });
    else setError("Unsupported form");
  }
  return (
    <div
      className="modal"
      role="dialog"
      aria-modal="true"
      aria-label={`Create ${type}`}
    >
      <div className="modal-header">
        <h2>
          {type === "slo"
            ? "Add SLO policy"
            : type === "change"
              ? "Record change"
              : "New dataset"}
        </h2>
        <button className="icon-button" onClick={onClose} aria-label="Close">
          <X size={18} />
        </button>
      </div>
      <form onSubmit={save}>
        <label>
          {type === "slo"
            ? "Agent name"
            : type === "change"
              ? "Change type"
              : "Dataset name"}
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={
              type === "change"
                ? "deployment"
                : type === "slo"
                  ? "refund-agent"
                  : "refund-scenarios"
            }
          />
        </label>
        {type === "change" && (
          <label>
            Subject name
            <input
              required
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="payments.refund"
            />
          </label>
        )}
        {type !== "dataset" && (
          <>
            <label>
              {type === "slo"
                ? "Minimum completion rate (0–1)"
                : "Before version"}
              <input
                required={type === "slo"}
                value={before}
                onChange={(e) => setBefore(e.target.value)}
                placeholder={type === "slo" ? "0.98" : "1.8.4"}
              />
            </label>
            <label>
              {type === "slo" ? "Maximum P95 latency (ms)" : "After version"}
              <input
                required={type === "slo"}
                value={after}
                onChange={(e) => setAfter(e.target.value)}
                placeholder={type === "slo" ? "8000" : "1.9.0"}
              />
            </label>
          </>
        )}
        {error && <div className="form-error">{error}</div>}
        <div className="modal-actions">
          <button type="button" className="button subtle" onClick={onClose}>
            Cancel
          </button>
          <button className="button primary">
            Save <Check size={15} />
          </button>
        </div>
      </form>
    </div>
  );
}
