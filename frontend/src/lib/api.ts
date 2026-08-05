import type {
  ApiErrorBody,
  AppConfig,
  CompareResponse,
  DemoJobAccepted,
  DemoState,
  HealthResponse,
  LineageGraphResponse,
  MetricsResponse,
  PostmortemRecord,
  RunEvent,
  RunRecord,
  Scenario,
  SignalsResponse,
} from "./types";

// Pinned to 127.0.0.1 rather than localhost: the backend binds IPv4 only, and browsers resolve
// localhost to ::1 first, so any unrelated process on [::1]:8001 silently answers every API call.
export const API_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly hint: string | null;

  constructor(status: number, body: ApiErrorBody) {
    super(body.error.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.error.code;
    this.hint = body.error.hint;
  }
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const error = value.error;
  return typeof error === "object" && error !== null && "code" in error && "message" in error;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    let value: unknown;
    try { value = await response.json(); } catch { value = null; }
    const body: ApiErrorBody = isApiErrorBody(value)
      ? value
      : { error: { code: "request_failed", message: `Request failed (${response.status})`, hint: null } };
    throw new ApiError(response.status, body);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  config: () => request<AppConfig>("/api/config"),
  signals: () => request<SignalsResponse>("/api/signals"),
  runs: (limit = 50) => request<RunRecord[]>(`/api/runs?limit=${limit}`),
  run: (id: string) => request<RunRecord>(`/api/runs/${encodeURIComponent(id)}`),
  runEvents: (id: string) => request<RunEvent[]>(`/api/runs/${encodeURIComponent(id)}/events`),
  createRun: (input: { dataset_urn: string; signal_kind: string; signal_detail?: string; assertion_urn?: string }) =>
    request<{ run_id: string }>("/api/runs", { method: "POST", body: JSON.stringify(input) }),
  metrics: () => request<MetricsResponse>("/api/metrics"),
  lineage: (wholeNamespace = true) => request<LineageGraphResponse>(`/api/lineage/graph?whole_namespace=${wholeNamespace}`),
  lineageFocus: (urn: string, up = 3, down = 3) => request<LineageGraphResponse>(`/api/lineage/graph?urn=${encodeURIComponent(urn)}&up=${up}&down=${down}`),
  demoState: () => request<DemoState>("/api/demo/state"),
  seed: () => request<DemoJobAccepted>("/api/demo/seed", { method: "POST", body: JSON.stringify({ wipe: false }) }),
  breakScenario: (scenario: Scenario) => request<DemoJobAccepted>("/api/demo/break", { method: "POST", body: JSON.stringify({ scenario }) }),
  reset: (keepMemory: boolean, purge = false) => request<DemoJobAccepted>("/api/demo/reset", { method: "POST", body: JSON.stringify({ keep_memory: keepMemory, purge }) }),
  postmortems: () => request<PostmortemRecord[]>("/api/postmortems"),
  postmortem: (id: string) => request<PostmortemRecord>(`/api/postmortems/${encodeURIComponent(id)}`),
  compare: (a?: string, b?: string) => request<CompareResponse>(a && b ? `/api/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}` : "/api/compare"),
};
