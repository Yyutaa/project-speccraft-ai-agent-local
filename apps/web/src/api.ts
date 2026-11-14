import type { Assumption, AssumptionResolution, ContextConflict, ContextConflictResolution, CreateContext, KnowledgeCitation, ResolutionEvidence, TdReviewProjection, TdReviewRecord, TdReviewRequest } from "./governance";

export type StageSummary = {
  id: string;
  title: string;
  description: string;
  implemented: boolean;
};

export type Scaffold = {
  project: string;
  mode: "project-scaffold";
  implemented_capabilities: string[];
  deferred_capabilities: string[];
  stages: StageSummary[];
};

export type Health = {
  status: "ok";
  service: string;
};

export type FactDimension = "role" | "workflow" | "permission" | "failure" | "acceptance";

export type ClarificationProposal = {
  question_id: string;
  target_kind?: "dimension" | "assumption" | "context_conflict";
  target_id?: string | null;
  object_revision?: number | null;
  gap_id: string;
  question: string;
  options: Array<{ option_id: string; label: string }>;
  recommended_option_id: string | null;
  recommendation_reason: string | null;
};

export type ClarificationAnswer = {
  question_id: string;
  selected_option_id?: string;
  custom_answer?: string;
  confirmed_candidate_id?: string;
};

export type SourceSnapshot = {
  source: { source_type: "inline_requirement" | "requirement_file" | "repository_guide" | "repository_metadata" | "business_knowledge"; path: string | null };
  normalized_path: string | null;
  sha256: string;
  read_status: "read";
  content: string;
};

export type SourceRecord = {
  source_id: string;
  run_id: string;
  repository_id: string | null;
  source_role: "inline_requirement" | "requirement_file" | "business_knowledge" | "repository_guide" | "repository_metadata";
  snapshot: SourceSnapshot;
};

export type PendingSourceClaim = {
  candidate_id: string;
  source_id: string;
  source_sha256: string;
  start: number;
  end: number;
  excerpt: string;
  candidate_revision: number;
  status: "pending" | "accepted" | "rejected";
};

export type SourceClaimReview = {
  review_id: string;
  candidate_id: string;
  candidate_revision: number;
  source_id: string;
  source_sha256: string;
} & ({ action: "reject" } | { action: "accept"; usage: "background_only"; dimension: null }
  | { action: "accept"; usage: "product"; dimension: FactDimension });

export type SourceAdmissionEvidence = {
  run_id: string;
  command_id: string;
  batch_id: string;
  batch_revision: number;
  expected_revision: number;
  actor_claim: string;
  rationale: string;
  user_confirmed: true;
  confirmed_at: string;
  review_id: string;
  candidate_id: string;
  candidate_revision: number;
  source_id: string;
  source_sha256: string;
  start: number;
  end: number;
  excerpt: string;
  action: "accept" | "reject";
  usage: "product" | "background_only" | null;
  dimension: FactDimension | null;
};

export type AuthorityTopic = "api" | "data" | "error" | "idempotency" | "permission" | "state" | "failure" | "non_functional";
export type ArtifactRef = {
  artifact_id: string;
  kind: "prd" | "td" | "delivery_spec";
  revision: number;
  content_hash: string;
  media_type: string;
};

export type Run = {
  workbench?: Omit<Workbench, "run">;
  managedConfirmation?: { actor_claim: string; rationale: string; user_confirmed: boolean };
  run_id: string;
  parent_run_id: string | null;
  prd_supporting_context: { knowledge_citations: KnowledgeCitation[]; assumptions: Assumption[] };
  knowledge_citations: KnowledgeCitation[];
  assumptions: Assumption[];
  context_conflicts: ContextConflict[];
  assumption_resolution_evidence: Array<ResolutionEvidence & { assumption_id: string; object_revision: number; action: string; resulting_assumption_id: string; resulting_revision: number; resulting_status: string }>;
  context_resolution_evidence: Array<ResolutionEvidence & { conflict_id: string; object_revision: number; action: string; excluded_reference_id: string | null }>;
  td_review: TdReviewProjection | null;
  td_review_records: TdReviewRecord[];
  td_revisions: Array<{ revision: number; content: string; content_hash: string; changed_section_id?: string | null; feedback?: string | null; actor_claim?: string | null; command_id?: string | null }>;
  td_readiness: { revision: number; content_hash: string; issues: Array<{ code: string; section_id: string | null }>; ready: boolean } | null;
  requirement: string;
  status: "context_preparing" | "td_preparing" | "awaiting_clarification" | "prd_preparing" | "prd_awaiting_approval" | "td_awaiting_decision" | "td_awaiting_approval" | "completed";
  prd_blueprint: {
    ledger_revision: number;
    authoritative_fact_ids: string[];
    sections: Array<{ section_id: string; title: string; applicable: boolean; fact_ids: string[]; applicability_reason: string | null }>;
  } | null;
  prd_revisions: Array<{ revision: number; content: string; content_hash: string; changed_section_id: string | null; feedback: string | null }>;
  prd_draft: { revision: number; content: string; content_hash: string } | null;
  prd_readiness: { revision: number; content_hash: string; issues: Array<{ code: string; section_id: string | null }> } | null;
  prd_approval: { revision: number; content_hash: string; actor: string; rationale: string; approved_at: string } | null;
  design_authority: {
    prd_revision: number;
    prd_content_hash: string;
    items: Array<{ authority_id: string; topic: AuthorityTopic; statement: string; source_fact_ids: string[]; source_prd_section_ids: string[] }>;
  } | null;
  td_blueprint: {
    prd_revision: number;
    prd_content_hash: string;
    authority_ids: string[];
    obligation_ids: string[];
    sections: Array<{ section_id: string; title: string; authority_ids: string[]; obligation_ids: string[] }>;
  } | null;
  technical_decision_requests: Array<{ request_id: string; topic: AuthorityTopic; question: string; options: string[]; reason: string }>;
  technical_decisions: Array<{ request_id: string; answer: string; actor: string }>;
  td_draft: {
    revision: number;
    content: string;
    content_hash: string;
    prd_revision: number;
    prd_content_hash: string;
    authority_pack_hash: string;
    obligations: Array<{ obligation_id: string; statement: string; prd_section_id: string; prd_section_hash: string; source_fact_ids: string[] }>;
  } | null;
  td_approval: { revision: number; content_hash: string; actor: string; rationale: string; approved_at: string } | null;
  delivery_spec: {
    schema_version: "1.0";
    run_id: string;
    prd: ArtifactRef;
    td: ArtifactRef;
    authority_pack_hash: string;
    obligations: Array<{ obligation_id: string; authority_topics: AuthorityTopic[]; td_section_ids: string[] }>;
  } | null;
  artifact_envelopes: Array<{
    artifact: ArtifactRef;
    derived_from: ArtifactRef[];
    approval: { revision: number; content_hash: string; actor: string; approved_at: string } | null;
    published_at: string;
  }>;
  quality_issues: Array<{ issue_id: string; producer_kind?: "deterministic" | "model"; disposition?: string; section_id: string; evidence: string; severity: "blocker" | "major"; status: "open" | "reopened" | "resolved" | "failed" | "accepted"; attempts: number; last_failure: string | null }>;
  quality_patch_attempts: Array<{ issue_id: string; command_id: string; outcome: "committed" | "rejected"; reason: string | null }>;
  quality_risk_acceptances: Array<{ issue_id: string; td_revision: number; actor_claim: string; rationale: string; disclosure_location: string; disclosure_text?: string }>;
  quality_issue_decisions?: Array<{ issue_id: string; td_revision: number; actor_claim: string; rationale: string; decision: string }>;
  quality_provider?: string | null;
  quality_audit_current?: boolean;
  quality_executions?: Array<{ command_id: string; provider_id: string; steps: number; outcome: string; reason: string; td_revision: number; input_bindings: string[]; observations: string[] }>;
  quality_audits?: Array<{ audit_id: string; td_revision: number; td_content_hash: string; passed: boolean; executor: string; semantic_mode: string; checks: string[]; ledger_hash: string }>;
  quality_gate: { td_revision: number; td_content_hash: string; authority_pack_hash: string; obligations_hash: string; status: "continue" | "diagnose" | "final_audit" | "ready"; blocking_issue_ids: string[] } | null;
  available_commands: Array<"decide_td_issue" | "run_td_quality" | "submit_clarification" | "revise_prd" | "approve_prd" | "submit_technical_decisions" | "record_td_review" | "revise_td" | "patch_td_issue" | "accept_td_quality_risk" | "approve_td">;
  source_records: SourceRecord[];
  pending_source_claims: PendingSourceClaim[];
  source_admission_evidence: SourceAdmissionEvidence[];
  source_snapshot: SourceSnapshot;
  repository_binding: {
    repository_id: string;
    root_path: string;
    permission: "read_only";
    context_mode: "guide_only" | "indexed_readonly";
  };
  harness_context: {
    entries: Array<{ snapshot: SourceSnapshot; selection_reason: string }>;
    sha256: string;
  };
  ledger: {
    revision: number;
    facts: Array<{
      fact_id: string;
      kind: "fact" | "decision";
      dimension: FactDimension | null;
      claim: string;
      source?: { sha256: string; excerpt: string } | null;
      source_id?: string | null;
      admission_evidence?: SourceAdmissionEvidence | null;
      decision_evidence?: {
        batch_id: string;
        question_id: string;
        command_id: string;
        expected_revision: number;
        answer: string;
        actor_claim: string;
        rationale: string;
        supporting_citation_ids: string[];
        resolved_assumption_ids: string[];
        decided_at: string;
      } | null;
    }>;
  };
  completeness: {
    ledger_revision: number;
    gaps: Array<{
      gap_id: string;
      dimension: FactDimension;
      blocking: boolean;
      reason: string;
      ledger_revision: number;
    }>;
  };
  clarification_batch: {
    batch_id: string;
    revision: number;
    ledger_revision: number;
    gap_ids: string[];
    blocking_gap_ids: string[];
    required_candidate_ids: string[];
    proposals: ClarificationProposal[];
  } | null;
};

export class WorkflowSyncPendingError extends Error {
  constructor(readonly runId: string) {
    super("命令已保存，但流程检查点尚未同步");
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = typeof body === "object" && body !== null && "detail" in body
      ? body.detail : null;
    const code = typeof detail === "object" && detail !== null && "code" in detail
      && typeof detail.code === "string" ? detail.code : null;
    if (response.status === 503 && code === "workflow_sync_pending"
      && typeof detail === "object" && detail !== null
      && "committed" in detail && detail.committed === true
      && "run_id" in detail && typeof detail.run_id === "string") {
      throw new WorkflowSyncPendingError(detail.run_id);
    }
    throw new Error(`请求失败：${response.status}${code ? ` · ${code}` : ""}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  readWorkbench: async (runId: string) => projectWorkbench(await request<Workbench>(`/api/runs/${encodeURIComponent(runId)}/workbench`)),
  createManagedRun: async (source: ({ requirement: string } | { requirement_path: string }) & CreateContext) => {
    const result = await request<{ run_id: string }>("/api/managed/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ execution_contract_version: 1, request: { governance_contract_version: 2, ...source } }) });
    return readAfterCommand(result.run_id);
  },
  controlJob: async (run: Run, jobId: string, action: "cancel" | "retry") => {
    const c = run.managedConfirmation;
    if (!c?.user_confirmed || !c.actor_claim.trim() || !c.rationale.trim()) throw new Error("请确认后台操作");
    await request<unknown>(`/api/managed/runs/${encodeURIComponent(run.run_id)}/jobs/${encodeURIComponent(jobId)}/${action}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ execution_contract_version: 1, governance_contract_version: 2, expected_run_version: run.workbench?.run_version, command_id: crypto.randomUUID(), ...c }) });
    return readAfterCommand(run.run_id);
  },
  health: () => request<Health>("/api/health"),
  scaffold: () => request<Scaffold>("/api/scaffold"),
  createRun: (source: ({ requirement: string } | { requirement_path: string }) & CreateContext) => request<Run>("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ governance_contract_version: 2, ...source }),
  }),
  readRun: (runId: string) => request<Run>(`/api/runs/${encodeURIComponent(runId)}`),
  revisePrd: (run: Run, sectionId: string, replacementBody: string, feedback: string) =>
    commandRequest(run, `/api/runs/${run.run_id}/prd/revisions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        governance_contract_version: 2,
        expected_revision: run.prd_draft?.revision,
        expected_content_hash: run.prd_draft?.content_hash,
        section_id: sectionId,
        replacement_body: replacementBody,
        feedback,
      }),
    }),
  approvePrd: (run: Run, actor: string, rationale: string) => commandRequest(run, `/api/runs/${run.run_id}/approvals/prd`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ governance_contract_version: 2, revision: run.prd_draft?.revision, content_hash: run.prd_draft?.content_hash, actor, rationale }),
  }),
  submitTechnicalDecisions: (run: Run, answers: Record<string, string>, actor: string) =>
    commandRequest(run, `/api/runs/${run.run_id}/technical-decisions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        governance_contract_version: 2,
        expected_prd_revision: run.prd_draft?.revision,
        expected_prd_content_hash: run.prd_draft?.content_hash,
        decisions: run.technical_decision_requests.map((item) => ({
          request_id: item.request_id,
          answer: answers[item.request_id],
          actor,
        })),
      }),
    }),
  submitClarification: (run: Run, answers: ClarificationAnswer[], sourceReviews: SourceClaimReview[],
    actorClaim: string, rationale: string, assumptionResolutions: AssumptionResolution[] = [],
    conflictResolutions: ContextConflictResolution[] = []) =>
    commandRequest(run, `/api/runs/${run.run_id}/clarifications/answers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        governance_contract_version: 2,
        expected_revision: run.ledger.revision,
        command_id: `${run.run_id}:clarification:${run.ledger.revision}`,
        batch_id: run.clarification_batch?.batch_id,
        batch_revision: run.clarification_batch?.revision,
        actor_claim: actorClaim,
        rationale,
        user_confirmed: true,
        source_reviews: sourceReviews,
        answers,
        ...(assumptionResolutions.length ? { assumption_resolutions: assumptionResolutions } : {}),
        ...(conflictResolutions.length ? { context_conflict_resolutions: conflictResolutions } : {}),
      }),
    }),
  recordTdReview: (run: Run, review: TdReviewRequest) => commandRequest(run, `/api/runs/${run.run_id}/td/reviews`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ governance_contract_version: 2, ...review }),
  }),
  reviseTd: (run: Run, sectionId: string, replacementBody: string, feedback: string, actorClaim: string, commandId: string) => commandRequest(run, `/api/runs/${run.run_id}/td/revisions`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ governance_contract_version: 2, command_id: commandId, section_id: sectionId, replacement_body: replacementBody, feedback, actor_claim: actorClaim,
      expected_td_revision: run.td_draft?.revision, expected_td_content_hash: run.td_draft?.content_hash, expected_review_revision: run.td_review?.review_revision }),
  }),
  decideTdIssue: (run: Run, issueId: string, actorClaim: string, rationale: string, commandId: string) => commandRequest(run, `/api/runs/${run.run_id}/td/quality/decisions`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ governance_contract_version: 2, command_id: commandId, actor_claim: actorClaim, rationale, issue_id: issueId, user_confirmed: true,
      expected_td_revision: run.td_draft?.revision, expected_td_content_hash: run.td_draft?.content_hash, expected_review_revision: run.td_review?.review_revision }),
  }),
  runTdQuality: (run: Run, actorClaim: string, maxSteps: number, commandId: string) => commandRequest(run, `/api/runs/${run.run_id}/td/quality/run`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ governance_contract_version: 2, command_id: commandId, actor_claim: actorClaim, max_steps: maxSteps,
      expected_td_revision: run.td_draft?.revision, expected_td_content_hash: run.td_draft?.content_hash, expected_review_revision: run.td_review?.review_revision }),
  }),
  patchTdIssue: (run: Run, issueId: string, sectionId: string, replacementBody: string, actorClaim: string, commandId: string) => commandRequest(run, `/api/runs/${run.run_id}/td/issues/patch`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ governance_contract_version: 2, command_id: commandId, issue_id: issueId, section_id: sectionId, replacement_body: replacementBody, actor_claim: actorClaim,
      expected_td_revision: run.td_draft?.revision, expected_td_content_hash: run.td_draft?.content_hash, expected_review_revision: run.td_review?.review_revision }),
  }),
  acceptTdQualityRisk: (run: Run, issueId: string, actorClaim: string, rationale: string, disclosureLocation: string, commandId: string) => commandRequest(run, `/api/runs/${run.run_id}/td/issues/accept-risk`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ governance_contract_version: 2, command_id: commandId, issue_id: issueId, actor_claim: actorClaim, rationale, disclosure_location: disclosureLocation,
      expected_td_revision: run.td_draft?.revision, expected_td_content_hash: run.td_draft?.content_hash }),
  }),
  approveTd: (run: Run, actor: string, rationale: string) => commandRequest(run, `/api/runs/${run.run_id}/approvals/td`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ governance_contract_version: 2, revision: run.td_draft?.revision, content_hash: run.td_draft?.content_hash, actor, rationale, review_id: run.td_review?.current_review_id, expected_review_revision: run.td_review?.review_revision }),
  }),
};

export type ModelBudget = { model_calls: number; candidates: number; policy: { max_model_calls: number; max_candidates: number } };
export type CommandReceipt = { command_id: string; kind: string; status: string; error_code: string | null; domain_committed: boolean; actor_claim: string | null; rationale: string | null };
export type JobSummary = { job_id: string; run_id: string; command_id: string; task_kind: string; status: string; error_code: string | null; run_version: number; available_commands: string[] };
export type Workbench = { run: Run; run_version: number; execution_mode: "managed" | "legacy"; available_commands: Run["available_commands"]; jobs: JobSummary[]; jobs_truncated?: boolean; command_receipts?: CommandReceipt[]; model_budget: ModelBudget | null; event_cursor: number };

function projectWorkbench(value: Workbench): Run {
  const { run, ...workbench } = value;
  return { ...run, workbench, available_commands: value.available_commands };
}
async function commandRequest(run: Run, path: string, init: RequestInit): Promise<Run> {
  if (run.workbench?.execution_mode !== "managed") return request<Run>(path, init);
  const confirmation = run.managedConfirmation;
  if (!confirmation?.user_confirmed || !confirmation.actor_claim.trim() || !confirmation.rationale.trim()) throw new Error("请填写后台操作责任者、理由并明确确认");
  const payload = JSON.parse(init.body as string) as Record<string, unknown>;
  const suffix = path.slice(`/api/runs/${run.run_id}`.length);
  const routes: Record<string, string> = { "/approvals/prd": "/prd/approve", "/approvals/td": "/td/approve", "/clarifications/answers": "/clarifications", "/td/issues/accept-risk": "/td/quality/risk-acceptances" };
  const target = routes[suffix] ?? suffix;
  const commandId = payload.command_id ?? crypto.randomUUID();
  const base = { execution_contract_version: 1, expected_run_version: run.workbench.run_version };
  const nested = { ...payload };
  // Existing forms carry their own responsibility claims; retain their exact values.
  const actor = String(payload.actor_claim ?? payload.actor ?? (Array.isArray(payload.decisions) ? payload.decisions[0]?.actor : undefined) ?? confirmation.actor_claim);
  const rationale = String(payload.rationale ?? confirmation.rationale);
  const body = suffix === "/clarifications/answers" ? { ...base, request: nested }
    : suffix === "/approvals/prd" ? { ...base, command_id: commandId, request: nested }
    : suffix === "/td/quality/run" ? { ...base, rationale, user_confirmed: true, request: nested }
    : { ...base, governance_contract_version: 2, command_id: commandId, actor_claim: actor, rationale, user_confirmed: true, request: nested };
  await request<unknown>(`/api/managed/runs/${encodeURIComponent(run.run_id)}${target}`, { ...init, body: JSON.stringify(body) });
  return readAfterCommand(run.run_id);
}

export function subscribeWorkbench(runId: string, cursor: number, refresh: () => void): () => void {
  let closed = false;
  let source: EventSource | undefined;
  let debounce: ReturnType<typeof setTimeout> | undefined;
  let retry: ReturnType<typeof setTimeout> | undefined;
  let poll: ReturnType<typeof setInterval> | undefined;
  let watchdog: ReturnType<typeof setInterval> | undefined;
  const schedule = () => { if (!debounce) debounce = setTimeout(() => { debounce = undefined; if (!closed) refresh(); }, 150); };
  const stop = () => {
    closed = true;
    source?.close();
    source = undefined;
    clearTimeout(debounce);
    clearTimeout(retry);
    clearInterval(poll);
    clearInterval(watchdog);
  };
  const connect = () => {
    if (closed) return;
    if (typeof EventSource === "undefined") { if (!poll) poll = setInterval(schedule, 5000); return; }
    const connection = new EventSource(`/api/runs/${encodeURIComponent(runId)}/events/stream?after=${cursor}`);
    source = connection;
    let lastActivity = Date.now();
    const isCurrent = () => !closed && source === connection;
    const recover = () => {
      if (!isCurrent()) return;
      connection.close();
      source = undefined;
      clearInterval(watchdog);
      if (!poll) poll = setInterval(schedule, 5000);
      clearTimeout(retry);
      retry = setTimeout(connect, 5000);
    };
    watchdog = setInterval(() => {
      if (isCurrent() && Date.now() - lastActivity >= 25000) recover();
    }, 5000);
    for (const kind of ["ready", "reset", "update", "terminal", "heartbeat"]) connection.addEventListener(kind, (event) => {
      if (!isCurrent()) return;
      lastActivity = Date.now();
      if (kind === "heartbeat") return;
      if (kind === "terminal") {
        connection.close();
        source = undefined;
        clearInterval(watchdog);
        clearTimeout(retry);
        clearInterval(poll);
        refresh();
        let attempts = 0;
        poll = setInterval(() => { if (++attempts >= 3) stop(); else refresh(); }, 5000);
        return;
      }
      const id = Number((event as MessageEvent).lastEventId);
      if (kind === "update" && id <= cursor) return;
      if (Number.isSafeInteger(id) && id >= 0) cursor = id;
      if (kind === "ready" || kind === "reset") { clearInterval(poll); poll = undefined; }
      schedule();
    });
    connection.onerror = recover;
  };
  connect();
  return stop;
}

export class ManagedReadPendingError extends Error {
  constructor(readonly runId: string) {
    super(`命令已受理（Run ${runId}），读取最新工作台失败；请按 ID 打开确认结果，不要重发写命令`);
  }
}
async function readAfterCommand(runId: string): Promise<Run> {
  try { return await api.readWorkbench(runId); }
  catch { throw new ManagedReadPendingError(runId); }
}
