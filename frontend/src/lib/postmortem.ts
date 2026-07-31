import type { BlastRadiusItem, CausalNode, JsonValue, PostmortemRecord } from "./types";

function isRecord(value: JsonValue | undefined): value is Record<string, JsonValue> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(record: Record<string, JsonValue>, key: string): string | null {
  const value = record[key];
  return typeof value === "string" ? value : null;
}

function numberValue(record: Record<string, JsonValue>, key: string): number | null {
  const value = record[key];
  return typeof value === "number" ? value : null;
}

export function postmortemCausalPath(postmortem: PostmortemRecord): CausalNode[] {
  const raw = postmortem.doc_json.causal_path;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((value) => {
    if (!isRecord(value)) return [];
    const urn = stringValue(value, "urn");
    const name = stringValue(value, "name");
    const hops = numberValue(value, "hops_from_symptom");
    const verdict = stringValue(value, "verdict");
    if (!urn || !name || hops === null || !verdict) return [];
    const rawEvidence = value.evidence;
    const evidence = Array.isArray(rawEvidence) ? rawEvidence.filter((item): item is string => typeof item === "string") : [];
    return [{ urn, name, hops_from_symptom: hops, verdict, evidence }];
  });
}

const entityTypes = new Set<BlastRadiusItem["entity_type"]>(["DATASET", "CHART", "DASHBOARD", "MLMODEL"]);
const severities = new Set<BlastRadiusItem["severity"]>(["critical", "high", "medium", "low"]);

export function postmortemBlastRadius(postmortem: PostmortemRecord): BlastRadiusItem[] {
  const raw = postmortem.doc_json.blast_radius;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((value) => {
    if (!isRecord(value)) return [];
    const urn = stringValue(value, "urn");
    const name = stringValue(value, "name");
    const entityType = stringValue(value, "entity_type");
    const hops = numberValue(value, "hops");
    const usage = numberValue(value, "usage_score");
    const severity = stringValue(value, "severity");
    if (!urn || !name || !entityType || !entityTypes.has(entityType as BlastRadiusItem["entity_type"]) || hops === null || usage === null || !severity || !severities.has(severity as BlastRadiusItem["severity"])) return [];
    const rawOwners = value.owners;
    const owners = Array.isArray(rawOwners) ? rawOwners.filter((item): item is string => typeof item === "string") : [];
    return [{ urn, name, entity_type: entityType as BlastRadiusItem["entity_type"], hops, usage_score: usage, owners, severity: severity as BlastRadiusItem["severity"] }];
  });
}

export function dataHubEntityUrl(baseUrl: string, urn: string): string {
  const route = urn.startsWith("urn:li:dataset:") ? "dataset" : urn.startsWith("urn:li:dashboard:") ? "dashboard" : urn.startsWith("urn:li:chart:") ? "chart" : urn.startsWith("urn:li:mlModel:") ? "mlModel" : urn.startsWith("urn:li:incident:") ? "incident" : urn.startsWith("urn:li:document:") ? "document" : "search";
  return `${baseUrl.replace(/\/$/, "")}/${route}/${urn}`;
}
