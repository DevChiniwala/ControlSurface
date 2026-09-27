"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  DatasetPanel,
  EvidencePanel,
  type DatasetItemRecord,
  type DatasetRecord,
  type EvidenceBundle,
} from "./inspector-panels";
import { SpanInspector } from "./span-inspector";
import { ExecutionFlow } from "./execution-flow";
import { SessionPanel, type SessionSummary } from "./session-panel";
import { CommandPalette } from "./command-palette";
import { usePanelFocus } from "./use-panel-focus";
import { AuthVisual, MobileHealthPreview } from "./auth-visual";
import { BrandIdentity, BrandMark } from "./brand";
import { ProductionHealthView } from "./production-health";
import { TracesView } from "./traces-view";
import { FailureClustersView } from "./failure-clusters-view";
import { ReleaseGatesView } from "./release-gates-view";
import type {
  Cluster,
  Health,
  Incident,
  IncidentSummary,
  OverviewData,
  Project,
  RecordValue,
  RegressionCandidate,
  RegressionReview,
  ReleaseSummary,
  SloViewData,
  Span,
  Trace,
  TraceDetail,
} from "./product-types";
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
  Menu,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  SlidersHorizontal,
  Workflow,
  X,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_CONTROL_API || "http://localhost:8000";
const MAX_TRACE_TREE_ROWS = 2_000;
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

const viewRoute: Record<Page, string> = {
  health: "/overview",
  traces: "/traces",
  sessions: "/sessions",
  clusters: "/failure-clusters",
  incidents: "/incidents",
  regressions: "/regressions",
  datasets: "/datasets",
  release: "/releases",
  changes: "/changes",
  slos: "/slos",
  keys: "/settings/api-keys",
};

function decodePathSegment(value: string): string | undefined {
  try {
    return decodeURIComponent(value);
  } catch {
    return undefined;
  }
}

function viewFromPath(pathname: string): { page: Page; entityId?: string } {
  const segments = pathname.split("/").filter(Boolean);
  const first = segments[0];
  const page: Page =
    first === "overview"
      ? "health"
      : first === "failure-clusters"
        ? "clusters"
        : first === "releases"
          ? "release"
          : first === "settings" && segments[1] === "api-keys"
            ? "keys"
            : (
                  [
                    "traces",
                    "sessions",
                    "incidents",
                    "regressions",
                    "datasets",
                    "changes",
                    "slos",
                  ] as Page[]
                ).includes(first as Page)
              ? (first as Page)
              : "health";
  const hasEntity = ["traces", "sessions", "incidents", "release"].includes(
    page,
  );
  return {
    page,
    entityId:
      hasEntity && segments[1] ? decodePathSegment(segments[1]) : undefined,
  };
}

const navigation: {
  label: string;
  items: { id: Page; label: string; icon: typeof Activity }[];
}[] = [
  {
    label: "WORKSPACE",
    items: [{ id: "health", label: "Overview", icon: Activity }],
  },
  {
    label: "OBSERVE",
    items: [
      { id: "traces", label: "Traces", icon: Workflow },
      { id: "sessions", label: "Sessions", icon: Layers3 },
    ],
  },
  {
    label: "EVALUATE",
    items: [{ id: "datasets", label: "Datasets", icon: Database }],
  },
  {
    label: "MONITOR",
    items: [{ id: "slos", label: "SLOs", icon: SlidersHorizontal }],
  },
  {
    label: "INCIDENTS",
    items: [
      { id: "incidents", label: "Incidents", icon: ShieldAlert },
      { id: "clusters", label: "Failure Clusters", icon: Fingerprint },
      { id: "changes", label: "Change Ledger", icon: GitBranch },
    ],
  },
  {
    label: "IMPROVE",
    items: [
      { id: "regressions", label: "Regression Cases", icon: ClipboardList },
    ],
  },
  {
    label: "RELEASE",
    items: [{ id: "release", label: "Release Gates", icon: Check }],
  },
  {
    label: "SETTINGS",
    items: [{ id: "keys", label: "API Keys", icon: KeyRound }],
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
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
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
    if (response.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new Event("controlsurface:unauthorized"));
    }
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
function usd(nano: number | undefined | null) {
  return nano == null ? "—" : `$${(nano / 1_000_000_000).toFixed(4)}`;
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
          <div className="auth-mobile-intro">
            <strong>
              Ship reliable <span>AI agents.</span>
            </strong>
            <p>Observe, evaluate, diagnose, and ship with confidence.</p>
          </div>
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
  embedded = false,
}: {
  detail: TraceDetail;
  onClose: () => void;
  onCreateRegression: (trace: TraceDetail) => void;
  embedded?: boolean;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const { closeRef, panelRef } = usePanelFocus(onClose, !embedded);
  const tree = useMemo(() => {
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
    const spanIds = new Set(detail.spans.map((span) => span.span_id));
    const roots = detail.spans
      .filter(
        (span) => !span.parent_span_id || !spanIds.has(span.parent_span_id),
      )
      .sort((left, right) => left.start_ns - right.start_ns);
    const seen = new Set<string>();
    const rows: { span: Span; depth: number; unlinked: boolean }[] = [];
    const append = (starts: Span[], unlinked: boolean) => {
      const stack = [...starts].reverse().map((span) => ({ span, depth: 0 }));
      while (stack.length && rows.length < MAX_TRACE_TREE_ROWS) {
        const item = stack.pop();
        if (!item || seen.has(item.span.span_id)) continue;
        seen.add(item.span.span_id);
        rows.push({ ...item, unlinked });
        const children = map.get(item.span.span_id) || [];
        for (let index = children.length - 1; index >= 0; index -= 1) {
          stack.push({ span: children[index], depth: item.depth + 1 });
        }
      }
    };
    append(roots, false);
    const unlinked = detail.spans
      .filter((span) => !seen.has(span.span_id))
      .sort((left, right) => left.start_ns - right.start_ns);
    append(unlinked, true);
    return {
      rows,
      hidden: Math.max(0, detail.spans.length - rows.length),
      firstRoot: roots[0],
    };
  }, [detail.spans]);
  const current =
    detail.spans.find((span) => span.span_id === selected) || detail.spans[0];
  return (
    <div className={`detail-overlay ${embedded ? "embedded" : ""}`}>
      <section
        className={`detail-panel ${embedded ? "trace-inline-inspector" : ""}`}
        ref={panelRef}
        role={embedded ? "region" : "dialog"}
        aria-modal={embedded ? undefined : true}
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
            {tree.firstRoot?.name || detail.spans[0]?.name || "Agent run"}
          </h2>
          <div className="detail-meta">
            <Badge
              value={
                detail.spans.some((s) => s.status === "error")
                  ? "error"
                  : "success"
              }
            />
            <span>
              {detail.total_span_count || detail.spans.length} spans
              {detail.truncated ? " · first 10,000 shown" : ""}
            </span>
            <span>
              {usd(
                detail.spans.some((span) => span.cost_nano_usd != null)
                  ? detail.spans.reduce(
                      (sum, span) => sum + (span.cost_nano_usd || 0),
                      0,
                    )
                  : null,
              )}
            </span>
          </div>
        </div>
        <div className="trace-layout">
          <div className="trace-tree">
            <div className="pane-label">EXECUTION</div>
            {tree.rows.map(({ span, depth, unlinked }, index) => (
              <div key={span.span_id}>
                {unlinked && !tree.rows[index - 1]?.unlinked && (
                  <div className="pane-label unlinked-label">
                    UNLINKED OR CYCLIC SPANS
                  </div>
                )}
                <button
                  className={`span-row ${current?.span_id === span.span_id ? "selected" : ""}`}
                  style={{ paddingLeft: 14 + Math.min(depth, 20) * 20 }}
                  onClick={() => setSelected(span.span_id)}
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
              </div>
            ))}
            {tree.hidden > 0 && (
              <p className="trace-flow-limit">
                {tree.hidden.toLocaleString()} additional spans are available
                through the API. The tree is bounded to keep inspection fast.
              </p>
            )}
          </div>
          <ExecutionFlow
            spans={detail.spans}
            selectedId={current?.span_id}
            onSelect={setSelected}
          />
          <div className="span-detail">
            <div className="pane-label">SPAN DETAIL</div>
            {current && <SpanInspector key={current.span_id} span={current} />}
          </div>
        </div>
      </section>
    </div>
  );
}

export default function ControlSurfaceApp() {
  const router = useRouter();
  const pathname = usePathname();
  const route = useMemo(() => viewFromPath(pathname), [pathname]);
  const page = route.page;
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [identityError, setIdentityError] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [resource, setResource] = useState<{
    projectId: string;
    page: Page;
    value: unknown;
  } | null>(null);
  const [detail, setDetail] = useState<TraceDetail | null>(null);
  const [selectedSession, setSelectedSession] = useState<SessionSummary | null>(
    null,
  );
  const [sessionRuns, setSessionRuns] = useState<Trace[]>([]);
  const [sessionLoading, setSessionLoading] = useState(false);
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
  const navigate = useCallback(
    (destination: Page, entityId?: string) => {
      const suffix = entityId ? `/${encodeURIComponent(entityId)}` : "";
      router.push(`${viewRoute[destination]}${suffix}`);
      setMenuOpen(false);
      setForm("");
    },
    [router],
  );

  const refreshIdentity = useCallback(async () => {
    setIdentityError("");
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
      const message = (e as Error).message;
      if (
        message === "Authentication required" ||
        message === "Browser session expired"
      ) {
        setProjects([]);
        setProjectId("");
        setConfigured(true);
        return;
      }
      setIdentityError(message);
      setConfigured(null);
    }
  }, []);
  useEffect(() => {
    void refreshIdentity();
  }, [refreshIdentity]);
  useEffect(() => {
    const expireSession = () => {
      csrfPromise = null;
      setProjects([]);
      setProjectId("");
      setConfigured(true);
    };
    window.addEventListener("controlsurface:unauthorized", expireSession);
    return () =>
      window.removeEventListener("controlsurface:unauthorized", expireSession);
  }, []);
  useEffect(() => {
    if (!menuOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [menuOpen]);
  useEffect(() => {
    if (!projectId) return;
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      } else if (event.key === "Escape") {
        setPaletteOpen(false);
      }
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, [projectId]);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    setResource(null);
    try {
      const base = `/api/projects/${projectId}`;
      const value =
        page === "health"
          ? await Promise.all([
              request<Health>(`${base}/health`),
              request<IncidentSummary[]>(`${base}/incidents`),
              request<Trace[]>(`${base}/traces`),
            ]).then(([health, incidents, traces]) => ({
              ...health,
              incidents,
              traces,
            }))
          : page === "slos"
            ? await Promise.all([
                request<RecordValue[]>(`${base}/slos`),
                request<Health>(`${base}/health`),
              ]).then(([policies, health]) => ({ policies, health }))
            : await request(`${base}/${pagePath[page]}`);
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

  function openTrace(id: string) {
    navigate("traces", id);
  }
  const loadTraceDetail = useCallback(
    (id: string) =>
      request<TraceDetail>(`/api/projects/${projectId}/traces/${id}`),
    [projectId],
  );
  function openSession(session: SessionSummary) {
    setSelectedSession(session);
    setSessionRuns([]);
    setSessionLoading(true);
    navigate("sessions", session.session_id);
  }
  function openIncident(id: string) {
    navigate("incidents", id);
  }
  async function createRegressionFromIncident(item: Incident) {
    const cluster = item.evidence_json?.cluster as RecordValue | undefined;
    const representatives = cluster?.representatives as
      RecordValue[] | undefined;
    const traceId = representatives?.[0]?.trace_id;
    if (typeof traceId !== "string") {
      setError(
        "This incident has no representative run to mine into a regression case.",
      );
      return;
    }
    try {
      const trace = await request<TraceDetail>(
        `/api/projects/${projectId}/traces/${traceId}`,
      );
      setIncident(null);
      setDetail(trace);
      await createRegression(trace);
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
  function openReleaseEvidence(id: string) {
    navigate("release", id);
  }
  useEffect(() => {
    if (!projectId) return;
    const entityId = route.entityId;
    let active = true;
    if (page !== "traces" || !entityId) setDetail(null);
    if (page !== "sessions" || !entityId) {
      setSelectedSession(null);
      setSessionRuns([]);
      setSessionLoading(false);
    }
    if (page !== "incidents" || !entityId) setIncident(null);
    if (page !== "release" || !entityId) setReleaseEvidence(null);
    if (!entityId) return;
    const selectedEntityId = entityId;

    async function loadEntity() {
      try {
        const base = `/api/projects/${projectId}`;
        if (page === "traces") {
          const value = await request<TraceDetail>(
            `${base}/traces/${selectedEntityId}`,
          );
          if (active) setDetail(value);
        } else if (page === "sessions") {
          if (active) setSessionLoading(true);
          const [summary, runs] = await Promise.all([
            request<SessionSummary>(
              `${base}/sessions/${encodeURIComponent(selectedEntityId)}`,
            ),
            request<Trace[]>(
              `${base}/traces?session=${encodeURIComponent(selectedEntityId)}&limit=200`,
            ),
          ]);
          if (active) {
            setSelectedSession(summary);
            setSessionRuns(runs);
            setSessionLoading(false);
          }
        } else if (page === "incidents") {
          const value = await request<Incident>(
            `${base}/incidents/${selectedEntityId}`,
          );
          if (active) setIncident(value);
        } else if (page === "release") {
          const value = await request<EvidenceBundle>(
            `${base}/release-evidence/${selectedEntityId}`,
          );
          if (active) setReleaseEvidence(value);
        }
      } catch (cause) {
        if (active) {
          setSessionLoading(false);
          setError((cause as Error).message);
        }
      }
    }
    void loadEntity();
    return () => {
      active = false;
    };
  }, [page, projectId, route.entityId]);
  async function submit(pathPart: string, body: RecordValue) {
    try {
      if (pathPart === "keys") {
        const result = await request<{ key: string }>(
          `/api/projects/${projectId}/keys`,
          { method: "POST", body: JSON.stringify(body) },
        );
        setKeyOnce(result.key);
      } else {
        await request(`/api/projects/${projectId}/${pathPart}`, {
          method: "POST",
          body: JSON.stringify(body),
        });
      }
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
    navigate("incidents");
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
      navigate("regressions");
      if (page === "regressions") void refresh();
    } catch (e) {
      setRegressionReview(
        (current) =>
          current && { ...current, saving: false, error: (e as Error).message },
      );
    }
  }
  async function logout() {
    try {
      await request("/api/logout", { method: "POST" });
      setProjects([]);
      setProjectId("");
      setConfigured(true);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (identityError)
    return (
      <div className="boot boot-error" role="alert">
        <BrandMark />
        <strong>ControlSurface is unavailable</strong>
        <span>{identityError}</span>
        <button
          className="button primary"
          onClick={() => void refreshIdentity()}
        >
          Retry connection
        </button>
      </div>
    );
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
      {menuOpen && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setMenuOpen(false)}
        />
      )}
      <aside
        id="primary-navigation"
        className={`sidebar ${menuOpen ? "mobile-open" : ""}`}
      >
        <div className="brand">
          <BrandIdentity />
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
              router.push(viewRoute[page]);
              setDataset(null);
              setReleaseEvidence(null);
              setDetail(null);
              setSelectedSession(null);
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
                      navigate(item.id);
                      setDetail(null);
                      setSelectedSession(null);
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
          <button
            className="icon-button mobile-menu-button"
            aria-label="Open navigation"
            aria-expanded={menuOpen}
            aria-controls="primary-navigation"
            onClick={() => setMenuOpen((open) => !open)}
          >
            <Menu size={18} />
          </button>
          <div className="breadcrumb">
            {project?.name}
            <ChevronRight size={14} />
            {title}
          </div>
          <div className="top-actions">
            <button
              className="command-trigger"
              aria-label="Open navigation search"
              onClick={() => setPaletteOpen(true)}
            >
              <Search size={14} />
              <span>Jump to</span>
              <kbd>Ctrl K</kbd>
            </button>
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
            <ProductionHealthView
              data={data as OverviewData | null}
              loading={loading}
              onOpenIncidents={() => navigate("incidents")}
              onOpenIncident={openIncident}
              onOpenTrace={openTrace}
              onOpenTraces={() => navigate("traces")}
              onOpenKeys={() => navigate("keys")}
            />
          )}
          {page === "traces" && (
            <TracesView
              traces={((data as Trace[] | null) || []).filter((trace) =>
                `${trace.root_name} ${trace.agent_name} ${trace.trace_id}`
                  .toLowerCase()
                  .includes(search.toLowerCase()),
              )}
              loading={loading}
              search={search}
              onSearch={setSearch}
              selectedTraceId={route.entityId}
              onOpenTrace={openTrace}
              onRefresh={() => void refresh()}
              detailPanel={
                detail ? (
                  <SpanTree
                    embedded
                    detail={detail}
                    onClose={() => navigate("traces")}
                    onCreateRegression={createRegression}
                  />
                ) : undefined
              }
            />
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
                ) : (data as SessionSummary[] | null)?.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Session</th>
                        <th>Runs</th>
                        <th>Errors</th>
                        <th>Cost</th>
                        <th>Last seen</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {(data as SessionSummary[]).map((s) => (
                        <tr key={s.session_id}>
                          <td>
                            <button
                              className="text-button row-link mono"
                              onClick={() => void openSession(s)}
                            >
                              {short(s.session_id, 24)}
                            </button>
                          </td>
                          <td>{s.trace_count}</td>
                          <td>{s.errors}</td>
                          <td>{usd(s.cost_nano_usd)}</td>
                          <td>{date(s.last_seen)}</td>
                          <td>
                            <ChevronRight size={15} />
                          </td>
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
            <FailureClustersView
              clusters={data as Cluster[] | null}
              loading={loading}
              onAnalyze={() => void refresh()}
              onCreateIncident={(signature) => void analyze(signature)}
              onOpenTrace={openTrace}
              loadTrace={loadTraceDetail}
            />
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
                ) : (data as IncidentSummary[] | null)?.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Incident</th>
                        <th>Severity</th>
                        <th>Agent</th>
                        <th>Status</th>
                        <th>Affected runs</th>
                        <th>Top evidence</th>
                        <th>Started</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {(data as IncidentSummary[]).map((item) => (
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
                          <td>{item.agent_name || "—"}</td>
                          <td>
                            <Badge value={item.status} />
                          </td>
                          <td>{item.affected_run_count.toLocaleString()}</td>
                          <td>
                            {item.top_evidence_subject ? (
                              <span className="evidence-summary">
                                <strong>{item.top_evidence_subject}</strong>
                                <small>
                                  {item.top_evidence_type || "change"}
                                  {item.top_evidence_score == null
                                    ? ""
                                    : ` · ${item.top_evidence_score.toFixed(2)}`}
                                </small>
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td>{date(item.started_at)}</td>
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
                        onClick={() => navigate("clusters")}
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
                        onClick={() => navigate("clusters")}
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
            <ReleaseGatesView
              releases={data as ReleaseSummary[] | null}
              loading={loading}
              selectedId={route.entityId}
              onSelect={openReleaseEvidence}
              detailPanel={
                releaseEvidence ? (
                  <EvidencePanel
                    embedded
                    bundle={releaseEvidence}
                    onClose={() => navigate("release")}
                  />
                ) : undefined
              }
            />
          )}
          {page === "slos" && (
            <>
              <SectionHeading
                eyebrow="MONITOR / LAST 24 HOURS"
                title="SLOs"
                description="Current reliability against each agent's configured production target."
                action={
                  <button
                    className="button primary"
                    onClick={() => setForm("slo")}
                  >
                    <Plus size={16} /> Add policy
                  </button>
                }
              />
              <div className="panel table-panel slo-table">
                {loading ? (
                  <div className="skeleton-row" />
                ) : (
                  (() => {
                    const view = data as SloViewData | null;
                    const policies = view?.policies || [];
                    return policies.length ? (
                      <table>
                        <thead>
                          <tr>
                            <th>Agent</th>
                            <th>Completion</th>
                            <th>Tool success</th>
                            <th>P95 latency</th>
                            <th>Samples</th>
                            <th>Health</th>
                          </tr>
                        </thead>
                        <tbody>
                          {policies.map((item) => {
                            const policy = item.policy_json as RecordValue;
                            const observed = view?.health.agents.find(
                              (agent) => agent.agent_name === item.agent_name,
                            );
                            return (
                              <tr key={String(item.agent_name)}>
                                <td className="strong">
                                  {String(item.agent_name)}
                                </td>
                                <td className="slo-measure">
                                  <strong>
                                    {observed
                                      ? `${(observed.completion_rate * 100).toFixed(1)}%`
                                      : "—"}
                                  </strong>
                                  <small>
                                    Target ≥{" "}
                                    {(
                                      Number(policy.completion_rate_min) * 100
                                    ).toFixed(1)}
                                    %
                                  </small>
                                </td>
                                <td className="slo-measure">
                                  <strong>
                                    {observed?.tool_success_rate == null
                                      ? "—"
                                      : `${(observed.tool_success_rate * 100).toFixed(1)}%`}
                                  </strong>
                                  <small>
                                    Target ≥{" "}
                                    {(
                                      Number(policy.tool_success_rate_min) * 100
                                    ).toFixed(1)}
                                    %
                                  </small>
                                </td>
                                <td className="slo-measure">
                                  <strong>
                                    {observed
                                      ? `${observed.p95_latency_ms} ms`
                                      : "—"}
                                  </strong>
                                  <small>
                                    Target ≤ {String(policy.p95_latency_ms_max)}{" "}
                                    ms
                                  </small>
                                </td>
                                <td className="slo-measure">
                                  <strong>{observed?.runs ?? 0}</strong>
                                  <small>
                                    Minimum {String(policy.minimum_samples)}
                                  </small>
                                </td>
                                <td>
                                  <Badge
                                    value={observed?.health || "no-data"}
                                  />
                                </td>
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
                    );
                  })()
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
                    onClick={() => setForm("key")}
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
      {paletteOpen && (
        <CommandPalette
          destinations={navigation.flatMap((group) =>
            group.items.map((item) => ({
              id: item.id,
              label: item.label,
              section: group.label,
            })),
          )}
          onSelect={(id) => {
            navigate(id as Page);
            setPaletteOpen(false);
            setMenuOpen(false);
            setDetail(null);
            setIncident(null);
            setSelectedSession(null);
          }}
          onClose={() => setPaletteOpen(false)}
        />
      )}
      {selectedSession && (
        <SessionPanel
          session={selectedSession}
          runs={sessionRuns}
          loading={sessionLoading}
          onClose={() => navigate("sessions")}
          onOpenTrace={(traceId) => {
            setSelectedSession(null);
            openTrace(traceId);
          }}
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
      {incident && (
        <div className="detail-overlay">
          <div className="detail-panel incident-panel">
            <div className="detail-top">
              <button
                className="icon-button"
                onClick={() => navigate("incidents")}
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
                {incident.agent_name && <span>{incident.agent_name}</span>}
              </div>
            </div>
            <div className="incident-content">
              <div className="incident-impact">
                <div>
                  <span>Affected runs</span>
                  <strong>{incident.affected_runs.toLocaleString()}</strong>
                </div>
                <div>
                  <span>First observed</span>
                  <strong>{date(incident.first_seen)}</strong>
                </div>
                <div>
                  <span>Latest observed</span>
                  <strong>{date(incident.last_seen)}</strong>
                </div>
              </div>
              <div className="incident-cluster-summary">
                <span className="eyebrow">DOMINANT FAILURE CLUSTER</span>
                <strong className="mono">
                  {short(incident.cluster_signature, 24)}
                </strong>
                <span>
                  Representative runs below provide the raw execution evidence.
                </span>
              </div>
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
                    <p>
                      {String(c.explanation || "Temporal association only")}
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
                    openTrace(String(r.trace_id));
                  }}
                >
                  {String(r.trace_id)} <ArrowRight size={15} />
                </button>
              ))}
              {(
                ((incident.evidence_json?.cluster as RecordValue)
                  ?.representatives as RecordValue[]) || []
              ).length > 0 && (
                <button
                  className="button primary incident-regression-action"
                  onClick={() => void createRegressionFromIncident(incident)}
                >
                  Create regression case <ArrowRight size={15} />
                </button>
              )}
              <h3 className="incident-timeline-title">Incident timeline</h3>
              <div className="incident-timeline">
                {[
                  ...(
                    (incident.evidence_json?.root_cause_candidates ||
                      []) as RecordValue[]
                  )
                    .slice(0, 1)
                    .filter(
                      (candidate) => typeof candidate.effective_at === "string",
                    )
                    .map((candidate) => ({
                      at: String(candidate.effective_at),
                      label: `${String(candidate.subject)} change recorded`,
                    })),
                  ...(incident.first_seen
                    ? [
                        {
                          at: incident.first_seen,
                          label: "Failure cluster first observed",
                        },
                      ]
                    : []),
                  { at: incident.created_at, label: "Incident opened" },
                  ...(incident.last_seen
                    ? [
                        {
                          at: incident.last_seen,
                          label: "Latest affected run observed",
                        },
                      ]
                    : []),
                ]
                  .sort((a, b) => Date.parse(a.at) - Date.parse(b.at))
                  .map((event, index) => (
                    <div key={`${event.label}-${index}`}>
                      <time dateTime={event.at}>{date(event.at)}</time>
                      <span>{event.label}</span>
                    </div>
                  ))}
              </div>
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
            onClose={() => {
              setRegressionReview(null);
              if (detail) navigate("traces", detail.trace_id);
            }}
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
  const { closeRef, panelRef } = usePanelFocus(onClose);
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("");
  const [before, setBefore] = useState("");
  const [after, setAfter] = useState("");
  const [error, setError] = useState("");
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    if (type === "dataset") await onSubmit("datasets", { name });
    else if (type === "key") await onSubmit("keys", { label: name });
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
    <section
      className="modal"
      role="dialog"
      aria-modal="true"
      aria-label={`Create ${type}`}
      ref={panelRef}
    >
      <div className="modal-header">
        <h2>
          {type === "key"
            ? "Create API key"
            : type === "slo"
              ? "Add SLO policy"
              : type === "change"
                ? "Record change"
                : "New dataset"}
        </h2>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="Close"
          ref={closeRef}
        >
          <X size={18} />
        </button>
      </div>
      <form onSubmit={save}>
        <label>
          {type === "key"
            ? "Key label"
            : type === "slo"
              ? "Agent name"
              : type === "change"
                ? "Change type"
                : "Dataset name"}
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={
              type === "key"
                ? "Local SDK"
                : type === "change"
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
        {type !== "dataset" && type !== "key" && (
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
            {type === "key" ? "Create key" : "Save"} <Check size={15} />
          </button>
        </div>
      </form>
    </section>
  );
}
