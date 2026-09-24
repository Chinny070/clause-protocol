import type { ConstitutionInput } from "../contract/calls";
import type { RemedyRow } from "../contract/types";

/**
 * Client-side PREVIEW of the contract's own constitution validation (contracts/clause_protocol.py::create_constitution,
 * _validate_clause_list, _validate_remedy_table, _check_remedy_completeness). The contract is authoritative; this only
 * lets the manufacturer see problems before signing an irreversible transaction.
 */
export interface Issue { field: string; message: string }

export const LIMITS = { clausesPerKind: 50, remedyRows: 50, categories: 20, shortLen: 200, textLen: 4000 } as const;

export interface Draft {
  version: string; productScope: string; coverageCalc: string;
  covered: { clause_id: string; text: string }[]; excluded: { clause_id: string; text: string }[];
  categories: string[]; sourcePolicy: string;
  claimDeadlineDays: number; responseDays: number; challengeWindowDays: number; challengeEnabled: boolean;
  insufficientBehavior: string; unavailableBehavior: string; expiryRules: string; remedy: RemedyRow[];
}

/** Remedy-table completeness (Stage 4.5): every reachable payable final state must resolve to a row. */
export function remedyCompleteness(rows: RemedyRow[], coveredIds: string[]): { complete: boolean; missing: string[] } {
  const pairs = new Set(rows.map((r) => `${r.outcome}|${r.clause_id}`));
  const missing: string[] = [];
  if (!pairs.has("ACCEPTED_NO_CONTEST|")) missing.push("An outcome-level ACCEPTED_NO_CONTEST row (a manufacturer can accept any claim).");
  if (!pairs.has("COVERED|")) {
    for (const id of coveredIds) if (!pairs.has(`COVERED|${id}`)) missing.push(`A COVERED row for clause ${id} (or one outcome-level COVERED row that covers every clause).`);
  }
  return { complete: missing.length === 0, missing };
}

function clauseIssues(kind: "covered" | "excluded", rows: { clause_id: string; text: string }[], out: Issue[]): void {
  const prefix = kind === "covered" ? "C-" : "X-";
  const field = `${kind} clauses`;
  if (kind === "covered" && rows.length < 1) out.push({ field, message: "A warranty must cover at least one clause." });
  if (rows.length > LIMITS.clausesPerKind) out.push({ field, message: `At most ${LIMITS.clausesPerKind} ${kind} clauses.` });
  const seen = new Set<string>();
  for (const r of rows) {
    if (!r.clause_id.startsWith(prefix) || r.clause_id.length > LIMITS.shortLen) out.push({ field, message: `Clause id "${r.clause_id}" must start with ${prefix}.` });
    if (r.text.trim() === "" || r.text.length > LIMITS.textLen) out.push({ field, message: `Clause ${r.clause_id || "(no id)"} needs text of 1–${LIMITS.textLen} characters.` });
    if (seen.has(r.clause_id)) out.push({ field, message: `Duplicate clause id ${r.clause_id}.` });
    seen.add(r.clause_id);
  }
}

export function validateDraft(d: Draft): Issue[] {
  const out: Issue[] = [];
  if (d.version.trim() === "") out.push({ field: "version", message: "Give this terms version a name (for example 2026.1)." });
  clauseIssues("covered", d.covered, out);
  clauseIssues("excluded", d.excluded, out);
  const allIds = [...d.covered, ...d.excluded].map((c) => c.clause_id);
  if (new Set(allIds).size !== allIds.length) out.push({ field: "clauses", message: "A clause id is used more than once." });
  if (d.categories.length < 1) out.push({ field: "evidence categories", message: "Define at least one evidence category." });
  if (d.categories.length > LIMITS.categories) out.push({ field: "evidence categories", message: `At most ${LIMITS.categories} categories.` });
  if (new Set(d.categories).size !== d.categories.length) out.push({ field: "evidence categories", message: "Duplicate evidence category." });
  for (const c of d.categories) if (c.trim() === "" || c.length > LIMITS.shortLen) out.push({ field: "evidence categories", message: "Categories must be 1–200 characters." });
  if (d.sourcePolicy.split(",").map((s) => s.trim()).filter(Boolean).length === 0) out.push({ field: "source policy", message: "List at least one permitted host, e.g. warranty.example.com or *.example.com." });
  if (d.remedy.length < 1) out.push({ field: "remedy table", message: "Add at least one remedy row." });
  if (d.remedy.length > LIMITS.remedyRows) out.push({ field: "remedy table", message: `At most ${LIMITS.remedyRows} remedy rows.` });
  const pairSeen = new Set<string>();
  for (const r of d.remedy) {
    const pair = `${r.outcome}|${r.clause_id}`;
    if (pairSeen.has(pair)) out.push({ field: "remedy table", message: `Duplicate remedy row for ${r.outcome}${r.clause_id ? " / " + r.clause_id : ""}.` });
    pairSeen.add(pair);
    if (r.clause_id !== "" && !allIds.includes(r.clause_id)) out.push({ field: "remedy table", message: `Remedy row cites unknown clause ${r.clause_id}.` });
    if (r.clause_id !== "" && r.outcome === "COVERED" && !r.clause_id.startsWith("C-")) out.push({ field: "remedy table", message: "A COVERED row must cite a covered (C-) clause." });
    if (r.clause_id !== "" && r.outcome === "NOT_COVERED" && !r.clause_id.startsWith("X-")) out.push({ field: "remedy table", message: "A NOT_COVERED row must cite an exclusion (X-) clause." });
    if (r.clause_id !== "" && r.outcome !== "COVERED" && r.outcome !== "NOT_COVERED") out.push({ field: "remedy table", message: `${r.outcome} rows are outcome-level (no clause).` });
    if (r.remedy_kind === "PARTIAL_BPS" && (r.remedy_value < 0n || r.remedy_value > 10000n)) out.push({ field: "remedy table", message: "Partial remedies are in basis points, 0–10000." });
    if (r.remedy_kind === "NONE" && r.remedy_value !== 0n) out.push({ field: "remedy table", message: "A NONE remedy must have value 0." });
  }
  const comp = remedyCompleteness(d.remedy, d.covered.map((c) => c.clause_id));
  for (const m of comp.missing) out.push({ field: "remedy table", message: `Incomplete remedy table: needs ${m}` });
  return out;
}

export function draftToInput(programId: number, d: Draft): ConstitutionInput {
  const day = 86400;
  return {
    programId, version: d.version.trim(), productScope: d.productScope, coverageCalc: d.coverageCalc,
    coveredClauses: d.covered, excludedClauses: d.excluded, acceptableEvidenceCategories: d.categories, sourceEligibilityPolicy: d.sourcePolicy.trim(),
    claimDeadlineS: Math.round(d.claimDeadlineDays * day), manufacturerResponsePeriodS: Math.round(d.responseDays * day),
    challengeWindowS: Math.round(d.challengeWindowDays * day), challengeDepth: d.challengeEnabled ? 1 : 0,
    insufficientEvidenceBehavior: d.insufficientBehavior, unavailableEvidenceBehavior: d.unavailableBehavior,
    expiryCancellationRules: d.expiryRules, remedyTable: d.remedy,
  };
}

/** Preview of the contract's source eligibility rule (https only; exact host, or *.base for subdomains but not the base). */
export function previewSourceEligibility(url: string, policy: string): { eligible: boolean; reason: string } {
  let u: URL;
  try { u = new URL(url); } catch { return { eligible: false, reason: "Not a valid URL." }; }
  if (u.protocol !== "https:") return { eligible: false, reason: "Only https:// sources are permitted." };
  const host = u.hostname.toLowerCase();
  const rules = policy.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
  for (const rule of rules) {
    if (rule.startsWith("*.")) { const base = rule.slice(2); if (host !== base && host.endsWith("." + base)) return { eligible: true, reason: `Matches ${rule}.` }; }
    else if (host === rule) return { eligible: true, reason: `Matches ${rule}.` };
  }
  return { eligible: false, reason: `Host ${host} is not permitted by the frozen source policy (${rules.join(", ") || "empty"}).` };
}

export function isRenderedCategory(category: string): boolean { return category.endsWith("_RENDERED"); }
