export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

export interface ApiErrorBody {
  error: { code: string; message: string; hint: string | null };
}

export interface HealthResponse {
  ok: boolean;
  version: string;
  datahub: { status: "up" | "down"; gms_url: string; server_version: string | null; seeded_entities: number };
  mcp: { status: "connected" | "unavailable"; tools: string[] };
  openai: { configured: boolean };
  db: { path: string; runs: number };
}

export interface AppConfig {
  datahub_ui_url: string;
  platform: string;
  scenarios: Scenario[];
  agent_model: string;
}

export type Scenario = "stale_upstream" | "recall_hit" | "schema_drift";

export interface SignalOwner {
  urn: string;
  name: string;
  email: string | null;
}

export interface Signal {
  id: string;
  dataset_urn: string;
  name: string;
  layer: string;
  kind: "assertion" | "freshness";
  severity: "critical" | "high" | "medium";
  title: string;
  detail: string;
  assertion_urns: string[];
  hours_stale: number | null;
  sla_hours: number | null;
  owners: SignalOwner[];
  detected_at: string;
  triaged_by_run_id: string | null;
}

export interface SignalsResponse {
  degraded: boolean;
  generated_at: string;
  signals: Signal[];
}

export type RunStatus = "running" | "succeeded" | "failed" | "cancelled";

export interface FindingData {
  urn: string;
  name: string;
  check: string;
  verdict: string;
  detail: string;
}

export interface CausalNode {
  urn: string;
  name: string;
  hops_from_symptom: number;
  verdict: string;
  evidence: string[];
}

export interface BlastRadiusItem {
  urn: string;
  name: string;
  entity_type: "DATASET" | "CHART" | "DASHBOARD" | "MLMODEL";
  hops: number;
  usage_score: number;
  owners: string[];
  severity: "critical" | "high" | "medium" | "low";
}

export interface ActionData {
  action: "incident" | "tag" | "notify" | "resolve";
  summary: string;
  urns: string[];
  datahub_url: string | null;
  detail: string;
  ok: boolean;
}

export interface RunRecord {
  id: string;
  created_at: string;
  finished_at: string | null;
  status: RunStatus;
  trigger_urn: string;
  trigger_name: string;
  signal_kind: string;
  signal_detail: string | null;
  scenario: string | null;
  root_cause_urn: string | null;
  root_cause_name: string | null;
  incident_urn: string | null;
  postmortem_id: string | null;
  summary: string | null;
  duration_s: number | null;
  time_to_root_cause_s: number | null;
  tool_calls: number;
  hops_walked: number;
  recall_used: number;
  recalled_ids: string[];
  causal_path: CausalNode[];
  blast_radius: BlastRadiusItem[];
  actions: ActionData[];
  findings: FindingData[];
  error: string | null;
}

export interface MetricsTrend {
  run_id: string;
  created_at: string;
  time_to_root_cause_s: number | null;
  tool_calls: number;
  recall_used: number;
}

export interface MetricsResponse {
  runs_total: number;
  runs_succeeded: number;
  avg_time_to_root_cause_s: number | null;
  median_tool_calls: number | null;
  recall_hit_rate: number;
  assets_protected: number;
  incidents_filed: number;
  postmortems_written: number;
  trend: MetricsTrend[];
}

export interface GraphOwner { urn: string; name: string }

export interface GraphNode {
  id: string;
  name: string;
  qualified_name: string;
  entity_type: "DATASET" | "CHART" | "DASHBOARD" | "MLMODEL";
  layer: "raw" | "staging" | "marts" | "ml" | "bi" | "unknown";
  platform: string;
  health: "healthy" | "degraded" | "broken" | "unknown";
  depth: number;
  row_count: number | null;
  hours_stale: number | null;
  sla_hours: number | null;
  queries_30d: number | null;
  weekly_views: number | null;
  failing_assertions: number;
  total_assertions: number;
  owners: GraphOwner[];
  datahub_url: string;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  columns: Array<{ from: string; to: string }>;
}

export interface LineageGraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  focus_urn: string | null;
}

export interface DemoState {
  seeded: boolean;
  entity_count: number;
  armed_scenario: Scenario | null;
  armed_at: string | null;
  healthy: boolean;
}

export interface DemoJobAccepted { job_id: string }

export interface DemoJobEvent {
  seq: number;
  job_id: string;
  kind: "progress" | "completed" | "error";
  line: string;
  step: number | null;
  total: number | null;
  returncode: number | null;
}

export interface PostmortemRecord {
  id: string;
  run_id: string;
  created_at: string;
  title: string;
  symptom: string | null;
  symptom_urn: string | null;
  root_cause_urn: string;
  root_cause_name: string | null;
  doc_markdown: string;
  doc_json: Record<string, JsonValue>;
  datahub_document_urn: string | null;
  datahub_links: string[];
  reused_count: number;
  used_by_runs: RunRecord[];
}

export interface CompareDelta { absolute: number | null; pct: number | null }
export interface CompareResponse {
  a: RunRecord;
  b: RunRecord;
  deltas: { time_to_root_cause_s: CompareDelta; tool_calls: CompareDelta; hops_walked: CompareDelta };
}

interface EventBase { seq: number; run_id: string; ts: string }
export interface RunStartedEvent extends EventBase {
  kind: "run_started";
  trigger: { dataset_urn: string; name: string; signal_kind: string; signal_detail: string };
  model: string;
}
export interface PhaseEvent extends EventBase { kind: "phase"; phase: string; note: string; phase_index: number }
export interface AgentMessageEvent extends EventBase { kind: "agent_message"; agent: string; text: string; delta: boolean }
export interface ReasoningEvent extends EventBase { kind: "reasoning"; agent: string; summary: string }
export interface ToolCallEvent extends EventBase {
  kind: "tool_call"; call_id: string; tool: string; origin: "mcp" | "native" | "subagent";
  args: Record<string, JsonValue>; agent: string;
}
export interface ToolResultEvent extends EventBase {
  kind: "tool_result"; call_id: string; tool: string; ok: boolean; duration_ms: number;
  summary: string; payload: JsonValue | null;
}
export interface RecallHit { incident_id: string; root_cause_name: string; relevance: number; hops_away: number }
export interface RecallEvent extends EventBase { kind: "recall"; found: number; top: RecallHit | null; all: RecallHit[] }
export interface FindingEvent extends EventBase, FindingData { kind: "finding" }
export interface CausalPathEvent extends EventBase { kind: "causal_path"; nodes: CausalNode[] }
export interface BlastRadiusEvent extends EventBase {
  kind: "blast_radius"; items: BlastRadiusItem[];
  totals: { datasets: number; charts: number; dashboards: number; models: number };
}
export interface ActionEvent extends EventBase, ActionData { kind: "action" }
export interface PostmortemEvent extends EventBase {
  kind: "postmortem"; postmortem_id: string; title: string;
  datahub_urls: { structured_property: string; document: string; link: string };
}
export interface MetricEvent extends EventBase { kind: "metric"; name: string; value: number | string }
export interface RunCompletedEvent extends EventBase {
  kind: "run_completed"; status: "succeeded" | "failed"; summary: string;
  metrics: { time_to_root_cause_s: number | null; tool_calls: number; hops_walked: number; recall_used: number };
  duration_s: number;
}
export interface ErrorEvent extends EventBase { kind: "error"; message: string; where: string }

export type RunEvent =
  | RunStartedEvent | PhaseEvent | AgentMessageEvent | ReasoningEvent | ToolCallEvent | ToolResultEvent
  | RecallEvent | FindingEvent | CausalPathEvent | BlastRadiusEvent | ActionEvent | PostmortemEvent
  | MetricEvent | RunCompletedEvent | ErrorEvent;
