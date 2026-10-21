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
};

export type SourceSnapshot = {
  source: { source_type: "inline_requirement" | "requirement_file" | "repository_guide" | "repository_metadata"; path: string | null };
  normalized_path: string | null;
  sha256: string;
  read_status: "read";
  content: string;
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
  run_id: string;
  requirement: string;
  status: "awaiting_clarification" | "prd_awaiting_approval" | "td_awaiting_decision" | "td_awaiting_approval" | "completed";
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
  available_commands: Array<"submit_clarification" | "revise_prd" | "approve_prd" | "submit_technical_decisions" | "approve_td">;
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
      decision_evidence?: {
        batch_id: string;
        question_id: string;
        command_id: string;
        expected_revision: number;
        answer: string;
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
    proposals: ClarificationProposal[];
  } | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/api/health"),
  scaffold: () => request<Scaffold>("/api/scaffold"),
  createRun: (source: { requirement: string } | { requirement_path: string }) => request<Run>("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(source),
  }),
  readRun: (runId: string) => request<Run>(`/api/runs/${encodeURIComponent(runId)}`),
  revisePrd: (run: Run, sectionId: string, replacementBody: string, feedback: string) =>
    request<Run>(`/api/runs/${run.run_id}/prd/revisions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_revision: run.prd_draft?.revision,
        expected_content_hash: run.prd_draft?.content_hash,
        section_id: sectionId,
        replacement_body: replacementBody,
        feedback,
      }),
    }),
  approvePrd: (run: Run, actor: string, rationale: string) => request<Run>(`/api/runs/${run.run_id}/approvals/prd`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ revision: run.prd_draft?.revision, content_hash: run.prd_draft?.content_hash, actor, rationale }),
  }),
  submitTechnicalDecisions: (run: Run, answers: Record<string, string>, actor: string) =>
    request<Run>(`/api/runs/${run.run_id}/technical-decisions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_prd_revision: run.prd_draft?.revision,
        expected_prd_content_hash: run.prd_draft?.content_hash,
        decisions: run.technical_decision_requests.map((item) => ({
          request_id: item.request_id,
          answer: answers[item.request_id],
          actor,
        })),
      }),
    }),
  submitClarification: (run: Run, answers: ClarificationAnswer[]) =>
    request<Run>(`/api/runs/${run.run_id}/clarifications/answers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_revision: run.ledger.revision,
        command_id: `${run.run_id}:clarification:${run.ledger.revision}`,
        answers,
      }),
    }),
  approveTd: (run: Run, actor: string, rationale: string) => request<Run>(`/api/runs/${run.run_id}/approvals/td`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ revision: run.td_draft?.revision, content_hash: run.td_draft?.content_hash, actor, rationale }),
  }),
};
