import { useEffect, useReducer, useRef } from "react";
import { API_URL, api } from "./api";
import type {
  ActionEvent,
  BlastRadiusItem,
  CausalNode,
  FindingEvent,
  PostmortemEvent,
  RecallEvent,
  RunEvent,
  RunStatus,
} from "./types";

export type StreamConnection = "connecting" | "live" | "reconnecting" | "closed" | "error";

export interface RunStreamState {
  status: RunStatus;
  phase: string;
  phaseIndex: number;
  events: RunEvent[];
  findings: FindingEvent[];
  causalPath: CausalNode[];
  blastRadius: BlastRadiusItem[];
  actions: ActionEvent[];
  recall: RecallEvent | null;
  postmortem: PostmortemEvent | null;
  metrics: Record<string, number | string | null>;
  connection: StreamConnection;
}

const initialState: RunStreamState = {
  status: "running",
  phase: "recall",
  phaseIndex: 0,
  events: [],
  findings: [],
  causalPath: [],
  blastRadius: [],
  actions: [],
  recall: null,
  postmortem: null,
  metrics: {},
  connection: "connecting",
};

type StreamAction =
  | { type: "EVENT"; event: RunEvent }
  | { type: "REPLAY"; events: RunEvent[] }
  | { type: "CONNECTION"; connection: StreamConnection };

function applyEvent(state: RunStreamState, event: RunEvent): RunStreamState {
  if (state.events.some((current) => current.seq === event.seq)) return state;
  const next: RunStreamState = { ...state, events: [...state.events, event].sort((a, b) => a.seq - b.seq) };
  switch (event.kind) {
    case "run_started": return { ...next, status: "running" };
    case "phase": return { ...next, phase: event.phase, phaseIndex: event.phase_index };
    case "finding": return { ...next, findings: [...state.findings, event] };
    case "causal_path": return { ...next, causalPath: event.nodes };
    case "blast_radius": return { ...next, blastRadius: event.items };
    case "action": return { ...next, actions: [...state.actions, event] };
    case "recall": return { ...next, recall: event };
    case "postmortem": return { ...next, postmortem: event };
    case "metric": return { ...next, metrics: { ...state.metrics, [event.name]: event.value } };
    case "run_completed": return {
      ...next,
      status: event.status,
      phase: "done",
      phaseIndex: 6,
      metrics: { ...state.metrics, ...event.metrics, duration_s: event.duration_s },
      connection: "closed",
    };
    default: return next;
  }
}

function replay(events: RunEvent[], connection: StreamConnection): RunStreamState {
  return [...events].sort((a, b) => a.seq - b.seq).reduce(applyEvent, { ...initialState, connection });
}

function runStreamReducer(state: RunStreamState, action: StreamAction): RunStreamState {
  if (action.type === "CONNECTION") return { ...state, connection: action.connection };
  if (action.type === "REPLAY") {
    const merged = new Map<number, RunEvent>();
    [...state.events, ...action.events].forEach((event) => merged.set(event.seq, event));
    return replay([...merged.values()], state.connection);
  }
  return applyEvent(state, action.event);
}

function isRunEvent(value: unknown): value is RunEvent {
  return typeof value === "object" && value !== null && "seq" in value && "run_id" in value && "ts" in value && "kind" in value;
}

const eventKinds = ["run_started", "phase", "agent_message", "reasoning", "tool_call", "tool_result", "recall", "finding", "causal_path", "blast_radius", "action", "postmortem", "metric", "run_completed", "error"] as const;

export function useRunStream(runId: string | undefined): RunStreamState {
  const [state, dispatch] = useReducer(runStreamReducer, initialState);
  const latestSeq = useRef(0);
  const reconciling = useRef(false);

  useEffect(() => {
    if (!runId) return;
    let active = true;
    let source: EventSource | null = null;
    latestSeq.current = 0;
    dispatch({ type: "CONNECTION", connection: "connecting" });

    const reconcile = async () => {
      if (reconciling.current) return;
      reconciling.current = true;
      try {
        const events = await api.runEvents(runId);
        if (!active) return;
        latestSeq.current = Math.max(latestSeq.current, 0, ...events.map((event) => event.seq));
        dispatch({ type: "REPLAY", events });
      } catch {
        if (active) dispatch({ type: "CONNECTION", connection: "error" });
      } finally { reconciling.current = false; }
    };

    const receive = (raw: Event) => {
      if (!(raw instanceof MessageEvent)) {
        dispatch({ type: "CONNECTION", connection: "reconnecting" });
        return;
      }
      let parsed: unknown;
      try { parsed = JSON.parse(String(raw.data)); } catch { return; }
      if (!isRunEvent(parsed)) return;
      if (parsed.seq > latestSeq.current + 1) void reconcile();
      latestSeq.current = Math.max(latestSeq.current, parsed.seq);
      dispatch({ type: "EVENT", event: parsed });
      if (parsed.kind === "run_completed") source?.close();
    };

    const connect = async () => {
      await reconcile();
      if (!active) return;
      const stored = await api.run(runId).catch(() => null);
      if (!active) return;
      if (stored && stored.status !== "running") {
        dispatch({ type: "CONNECTION", connection: "closed" });
        return;
      }
      source = new EventSource(`${API_URL}/api/runs/${encodeURIComponent(runId)}/stream`);
      source.onopen = () => dispatch({ type: "CONNECTION", connection: "live" });
      eventKinds.forEach((kind) => source?.addEventListener(kind, receive));
    };

    void connect();
    return () => {
      active = false;
      source?.close();
      reconciling.current = false;
    };
  }, [runId]);

  return state;
}
