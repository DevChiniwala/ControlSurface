import type { InspectedSpan } from "./span-inspector";

export type RecordValue = Record<string, unknown>;

export type Project = { id: string; name: string; slug: string };

export type Trace = {
  trace_id: string;
  agent_name: string;
  agent_version?: string | null;
  root_name: string;
  start_time: string;
  duration_ms: number | null;
  span_count: number;
  error_count: number;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cost_nano_usd: number | null;
  status: string;
  session_id: string;
};

export type Span = InspectedSpan & { parent_span_id: string };

export type TraceDetail = {
  trace_id: string;
  spans: Span[];
  total_span_count: number;
  truncated: boolean;
  graph: RecordValue | null;
  features: RecordValue | null;
};

export type AgentHealth = {
  agent_name: string;
  runs: number;
  failed_runs: number;
  completion_rate: number;
  tool_success_rate: number | null;
  tool_calls: number;
  p95_latency_ms: number | null;
  cost_nano_usd: number | null;
  average_cost_nano_usd?: number | null;
  health: string;
  breaches: string[];
  last_seen: string;
};

export type HealthSummary = {
  agent_count: number;
  healthy_agent_count: number;
  observed_run_count: number;
  failed_run_count: number;
  completion_rate: number | null;
  p95_latency_ms: number | null;
  recorded_cost_nano_usd: number | null;
};

export type Health = {
  window_hours: number;
  agents: AgentHealth[];
  open_incidents: number;
  summary: HealthSummary;
};

export type IncidentSummary = {
  id: string;
  title: string;
  agent_name: string | null;
  affected_run_count: number;
  severity: string;
  status: string;
  started_at: string;
  last_seen?: string;
  created_at: string;
  cluster_signature: string;
  top_evidence_type: string | null;
  top_evidence_subject: string | null;
  top_evidence_score: number | null;
};

export type Incident = {
  id: string;
  title: string;
  severity: string;
  status: string;
  affected_runs: number;
  created_at: string;
  first_seen?: string;
  last_seen?: string;
  agent_name?: string;
  evidence_json?: RecordValue;
  cluster_signature: string;
};

export type OverviewData = Health & {
  incidents: IncidentSummary[];
  traces: Trace[];
};

export type SloViewData = {
  policies: RecordValue[];
  health: Health;
};

export type Cluster = {
  signature: string;
  count: number;
  first_seen: string;
  last_seen: string;
  features: RecordValue;
  representatives: { trace_id: string; run_id: string }[];
};

export type ReleaseSummary = {
  id: string;
  decision: "passed" | "blocked";
  candidate_version: string;
  baseline_version: string;
  quality_delta: number | null;
  cost_delta: number | null;
  latency_delta: number | null;
  tool_accuracy_delta: number | null;
  failed_gate_count: number;
  evidence_hash: string;
  created_at: string;
};

export type RegressionCandidate = {
  name: string;
  source_trace_id: string;
  cluster_signature: string | null;
  input: RecordValue;
  expect: RecordValue;
  review_required: boolean;
  evidence?: RecordValue;
};

export type RegressionReview = {
  candidate: RegressionCandidate;
  name: string;
  input: string;
  expect: string;
  loading: boolean;
  notice: string;
  error: string;
  saving: boolean;
};
