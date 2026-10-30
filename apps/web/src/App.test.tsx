import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import App from "./App";
import type { Run, SourceSnapshot, PendingSourceClaim, SourceAdmissionEvidence } from "./api";

const scaffold = {
  project: "SpecCraft AI Agent",
  mode: "project-scaffold",
  implemented_capabilities: ["进程内存 Run"],
  deferred_capabilities: ["持久化 Run"],
  stages: [{ id: "prd", title: "产品规格设计", description: "编制 PRD。", implemented: false }],
};

const proposals = [
  ["role", "谁使用？", "administrator", "管理员"],
  ["workflow", "主要流程是什么？", "single_step", "单步骤流程"],
  ["permission", "如何限制权限？", "role_based", "按角色限制"],
  ["failure", "失败时如何处理？", "stop", "停止并提示错误"],
  ["acceptance", "如何验收？", "testable", "使用可验证的验收条件"],
].map(([dimension, question, optionId, label]) => ({
  question_id: `gap-${dimension}`,
  gap_id: `gap-${dimension}`,
  question,
  options: [
    { option_id: optionId, label },
    { option_id: `${optionId}-other`, label: `其他 ${label}` },
  ],
  recommended_option_id: optionId,
  recommendation_reason: "仅供参考，等待用户明确选择。",
}));

const sourceSnapshot: SourceSnapshot = {
  source: { source_type: "inline_requirement", path: null },
  normalized_path: null,
  sha256: "a".repeat(64),
  read_status: "read",
  content: "做一个问候页面",
};
const candidate: PendingSourceClaim = {
  candidate_id: "candidate-1", source_id: "source-1", source_sha256: "a".repeat(64),
  start: 0, end: 7, excerpt: "做一个问候页面", candidate_revision: 1, status: "pending",
};
const admissionEvidence: SourceAdmissionEvidence = {
  run_id: "run-1", command_id: "clarification-1", batch_id: "batch-1", batch_revision: 1,
  expected_revision: 1, actor_claim: "需求负责人", rationale: "逐项审阅", user_confirmed: true,
  confirmed_at: "2026-10-29T00:00:00Z", review_id: "review-1", candidate_id: candidate.candidate_id, candidate_revision: candidate.candidate_revision,
  source_id: candidate.source_id, source_sha256: candidate.source_sha256,
  start: candidate.start, end: candidate.end, excerpt: candidate.excerpt,
  action: "reject", usage: null, dimension: null,
};

function run(status: Run["status"]): Run {
  const awaiting = status === "awaiting_clarification";
  const base: Run = {
    run_id: "run-1",
    parent_run_id: null, prd_supporting_context: { knowledge_citations: [], assumptions: [] }, knowledge_citations: [], assumptions: [], context_conflicts: [], assumption_resolution_evidence: [], context_resolution_evidence: [], td_review: null, td_review_records: [], td_revisions: [], td_readiness: null,
    requirement: "做一个问候页面",
    status,
    prd_blueprint: awaiting ? null : { ledger_revision: 2, authoritative_fact_ids: proposals.map((p) => `decision-${p.gap_id}`), sections: [{ section_id: "acceptance", title: "验收标准", applicable: true, fact_ids: [], applicability_reason: null }] },
    prd_revisions: awaiting ? [] : [{ revision: 1, content: "# PRD\n问候页面", content_hash: "a".repeat(64), changed_section_id: null, feedback: null }],
    prd_draft: awaiting ? null : { revision: 1, content: "# PRD\n问候页面", content_hash: "a".repeat(64) },
    prd_readiness: awaiting ? null : { revision: 1, content_hash: "a".repeat(64), issues: [] },
    prd_approval: null,
    design_authority: null,
    td_blueprint: null,
    technical_decision_requests: [],
    technical_decisions: [],
    td_draft: null,
    td_approval: null,
    delivery_spec: null,
    artifact_envelopes: [],
    available_commands: awaiting ? ["submit_clarification"] : ["revise_prd", "approve_prd"],
    ledger: {
      revision: awaiting ? 1 : 2,
      facts: awaiting
        ? []
        : [
          ...proposals.map((proposal) => ({
            fact_id: `decision-${proposal.gap_id}`,
            kind: "decision" as const,
            dimension: proposal.gap_id.slice(4) as Run["completeness"]["gaps"][number]["dimension"],
            claim: proposal.options[0].label,
            source: null, source_id: null, admission_evidence: null,
            decision_evidence: {
              batch_id: "batch-1", question_id: proposal.question_id, command_id: "clarification-1",
              expected_revision: 1, answer: proposal.options[0].label,
              actor_claim: "需求负责人", rationale: "逐项审阅", supporting_citation_ids: [],
              resolved_assumption_ids: [], decided_at: "2026-10-29T00:00:00Z",
            },
          })),
        ],
    },
    completeness: {
      ledger_revision: awaiting ? 1 : 2,
      gaps: awaiting ? proposals.map((proposal) => ({
        gap_id: proposal.gap_id,
        dimension: proposal.gap_id.slice(4) as Run["completeness"]["gaps"][number]["dimension"],
        blocking: true,
        reason: "缺少信息",
        ledger_revision: 1,
      })) : [],
    },
    clarification_batch: awaiting ? {
      batch_id: "batch-1",
      revision: 1,
      ledger_revision: 1,
      gap_ids: proposals.map((proposal) => proposal.gap_id),
      blocking_gap_ids: proposals.map((proposal) => proposal.gap_id),
      proposals,
      required_candidate_ids: ["candidate-1"],
    } : null,
    source_records: [{ source_id: "source-1", run_id: "run-1", repository_id: null,
      source_role: "inline_requirement", snapshot: sourceSnapshot }],
    pending_source_claims: [{ ...candidate, status: awaiting ? "pending" : "rejected" }],
    source_admission_evidence: awaiting ? [] : [admissionEvidence],
    source_snapshot: {
      source: { source_type: "inline_requirement", path: null },
      normalized_path: null,
      sha256: "a".repeat(64),
      read_status: "read",
      content: "做一个问候页面",
    },
    repository_binding: {
      repository_id: "exportflow-sample",
      root_path: "/workspace/exportflow-sample",
      permission: "read_only",
      context_mode: "guide_only",
    },
    harness_context: {
      entries: [{
        snapshot: {
          source: { source_type: "repository_guide", path: "AGENTS.md" },
          normalized_path: "AGENTS.md",
          sha256: "b".repeat(64),
          read_status: "read",
          content: "技术约束",
        },
        selection_reason: "repository guide supplies engineering constraints",
      }],
      sha256: "c".repeat(64),
    },
  };
  if (status === "td_awaiting_approval") {
    return {
      ...base,
      prd_approval: { revision: 1, content_hash: "a".repeat(64), actor: "审阅人", rationale: "同意", approved_at: "2026-10-12T00:00:00Z" },
      design_authority: { prd_revision: 1, prd_content_hash: "a".repeat(64), items: [] },
      td_blueprint: { prd_revision: 1, prd_content_hash: "a".repeat(64), authority_ids: [], obligation_ids: [], sections: [] },
      td_draft: { revision: 1, content: "# TD\n使用 React", content_hash: "d".repeat(64), prd_revision: 1, prd_content_hash: "a".repeat(64), authority_pack_hash: "c".repeat(64), obligations: [] },
      td_review: { binding: { run_id: "run-1", prd_revision: 1, prd_content_hash: "a".repeat(64), td_revision: 1, td_content_hash: "d".repeat(64), authority_pack_hash: "c".repeat(64), obligations_hash: "e".repeat(64) }, status: "ready", current_review_id: "review-td-1", review_revision: 1, blocking_finding_ids: [] },
      available_commands: ["approve_td"],
    };
  }
  if (status === "completed") {
    return {
      ...base,
      prd_approval: { revision: 1, content_hash: "a".repeat(64), actor: "审阅人", rationale: "同意", approved_at: "2026-10-12T00:00:00Z" },
      design_authority: { prd_revision: 1, prd_content_hash: "a".repeat(64), items: [] },
      td_blueprint: { prd_revision: 1, prd_content_hash: "a".repeat(64), authority_ids: [], obligation_ids: [], sections: [] },
      td_draft: { revision: 1, content: "# TD\n使用 React", content_hash: "d".repeat(64), prd_revision: 1, prd_content_hash: "a".repeat(64), authority_pack_hash: "c".repeat(64), obligations: [] },
      td_approval: { revision: 1, content_hash: "d".repeat(64), actor: "技术审阅人", rationale: "同意", approved_at: "2026-10-12T00:01:00Z" },
      delivery_spec: {
        schema_version: "1.0", run_id: "run-1", authority_pack_hash: "c".repeat(64), obligations: [],
        prd: { artifact_id: "run-1:prd", kind: "prd", revision: 1, content_hash: "a".repeat(64), media_type: "text/markdown" },
        td: { artifact_id: "run-1:td", kind: "td", revision: 1, content_hash: "d".repeat(64), media_type: "text/markdown" },
      },
      artifact_envelopes: [],
      available_commands: [],
    };
  }
  return base;
}

function installApi(fetcher: typeof fetch) {
  vi.stubGlobal("fetch", fetcher);
}

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

async function chooseSourceReview(answer: string) {
  const group = screen.getByRole("group", { name: "来源候选 candidate-1" });
  fireEvent.mouseDown(within(group).getByRole("combobox"));
  fireEvent.click(await screen.findByRole("option", { name: answer }));
}

function confirmClarification() {
  fireEvent.change(screen.getByRole("textbox", { name: "需求决策者" }), { target: { value: "需求负责人" } });
  fireEvent.change(screen.getByRole("textbox", { name: "需求决策理由" }), { target: { value: "逐项审阅" } });
  fireEvent.click(screen.getByRole("checkbox", { name: "我确认这是本人明确提交的来源处理与需求决定" }));
}

async function chooseAnswer(question: string, answer: string) {
  const group = screen.getByRole("group", { name: question });
  fireEvent.mouseDown(within(group).getByRole("combobox"));
  fireEvent.click(await screen.findByRole("option", { name: answer }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("runs the PRD-first happy path from API-projected state", async () => {
  let current = run("awaiting_clarification");
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === "/api/health") return json({ status: "ok", service: "speccraft-project-scaffold" });
    if (path === "/api/scaffold") return json(scaffold);
    if (path === "/api/runs" && init?.method === "POST") return json(current, 201);
    if (path.endsWith("/clarifications/answers")) {
      current = run("prd_awaiting_approval");
      return json(current);
    }
    if (path.endsWith("/approvals/prd")) {
      current = run("td_awaiting_approval");
      return json(current);
    }
    if (path.endsWith("/approvals/td")) {
      current = run("completed");
      return json(current);
    }
    return json(current);
  });
  installApi(fetcher as typeof fetch);
  render(<App />);

  expect(await screen.findByText("API 已连接")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("一句话需求"), { target: { value: "做一个问候页面" } });
  fireEvent.click(screen.getByRole("button", { name: "创建 Run" }));
  expect(await screen.findByText("等待用户澄清需求")).toBeInTheDocument();
  expect(screen.queryByText("# PRD 问候页面")).not.toBeInTheDocument();
  expect(screen.getByText("只读工程上下文 · guide_only")).toBeInTheDocument();
  expect(screen.getByText("AGENTS.md")).toBeInTheDocument();
  expect(screen.getByText(/repository guide supplies engineering constraints/)).toBeInTheDocument();
  expect(screen.getByText(`SHA-256 ${"b".repeat(64)}`)).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledWith("/api/runs", expect.objectContaining({
    method: "POST",
    body: JSON.stringify({ governance_contract_version: 2, requirement: "做一个问候页面" }),
  }));

  const submitAnswers = screen.getByRole("button", { name: "提交澄清回答" });
  expect(submitAnswers).toBeDisabled();
  const firstQuestionGroup = screen.getByRole("group", { name: proposals[0].question });
  expect(within(firstQuestionGroup).getByRole("combobox")).toHaveAttribute("aria-expanded", "false");
  expect(within(firstQuestionGroup).getByText("请选择答案")).toBeInTheDocument();
  expect(screen.queryByRole("textbox", { name: `自定义回答：${proposals[0].question}` })).not.toBeInTheDocument();
  for (const proposal of proposals) {
    await chooseAnswer(proposal.question, `推荐：${proposal.options[0].label}`);
  }
  expect(submitAnswers).toBeDisabled();
  await chooseSourceReview("拒绝此来源候选");
  confirmClarification();
  expect(submitAnswers).toBeEnabled();
  fireEvent.click(submitAnswers);
  expect(await screen.findByText("等待 PRD 人工审批")).toBeInTheDocument();
  expect(screen.getByText("# PRD 问候页面")).toBeInTheDocument();
  const answerCall = fetcher.mock.calls.find(([input]) => String(input).endsWith("/clarifications/answers"));
  expect(answerCall?.[1]).toEqual(expect.objectContaining({
    method: "POST",
    body: expect.stringContaining('"expected_revision":1'),
  }));

  fireEvent.change(screen.getByRole("textbox", { name: "审批人" }), { target: { value: "审阅人" } });
  fireEvent.change(screen.getByRole("textbox", { name: "审批理由" }), { target: { value: "同意当前版本" } });
  fireEvent.click(screen.getByRole("button", { name: "批准 PRD" }));
  expect(await screen.findByText("等待 TD 人工审批")).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledWith("/api/runs/run-1/approvals/prd", expect.objectContaining({
    body: JSON.stringify({ governance_contract_version: 2, revision: 1, content_hash: "a".repeat(64), actor: "审阅人", rationale: "同意当前版本" }),
  }));
  expect(screen.getByText("# TD 使用 React")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("textbox", { name: "TD 审批人" }), { target: { value: "技术审阅人" } });
  fireEvent.change(screen.getByRole("textbox", { name: "TD 审批理由" }), { target: { value: "同意当前技术方案" } });
  fireEvent.click(screen.getByRole("button", { name: "批准 TD" }));
  expect(await screen.findByText("已完成")).toBeInTheDocument();
  expect(screen.getByText(/\"schema_version\": \"1.0\"/)).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledWith("/api/runs/run-1/approvals/td", expect.objectContaining({
    method: "POST",
    body: JSON.stringify({ governance_contract_version: 2, revision: 1, content_hash: "d".repeat(64), actor: "技术审阅人", rationale: "同意当前技术方案", review_id: "review-td-1", expected_review_revision: 1 }),
  }));
});

test("keeps the last server state when an approval is rejected", async () => {
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === "/api/health") return json({ status: "ok", service: "speccraft-project-scaffold" });
    if (path === "/api/scaffold") return json(scaffold);
    if (path === "/api/runs" && init?.method === "POST") return json(run("awaiting_clarification"), 201);
    if (path.endsWith("/clarifications/answers")) return json({ detail: { code: "invalid_clarification" } }, 422);
    if (path.endsWith("/approvals/prd")) return json({ detail: { code: "invalid_transition" } }, 409);
    return json(run("prd_awaiting_approval"));
  });
  installApi(fetcher as typeof fetch);
  render(<App />);

  expect(await screen.findByText("API 已连接")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("一句话需求"), { target: { value: "做一个问候页面" } });
  fireEvent.click(screen.getByRole("button", { name: "创建 Run" }));
  expect(await screen.findByText("等待用户澄清需求")).toBeInTheDocument();
  await chooseAnswer(proposals[0].question, "其他，自定义回答");
  const customAnswer = screen.getByRole("textbox", { name: `自定义回答：${proposals[0].question}` });
  fireEvent.change(customAnswer, { target: { value: "由项目管理员负责" } });
  await chooseAnswer(proposals[0].question, `推荐：${proposals[0].options[0].label}`);
  expect(screen.queryByRole("textbox", { name: `自定义回答：${proposals[0].question}` })).not.toBeInTheDocument();
  await chooseAnswer(proposals[0].question, "其他，自定义回答");
  expect(screen.getByRole("textbox", { name: `自定义回答：${proposals[0].question}` })).toHaveValue("");
  fireEvent.change(screen.getByRole("textbox", { name: `自定义回答：${proposals[0].question}` }), {
    target: { value: "由项目管理员负责" },
  });
  for (const proposal of proposals.slice(1)) {
    await chooseAnswer(proposal.question, `推荐：${proposal.options[0].label}`);
  }
  await chooseSourceReview("拒绝此来源候选");
  confirmClarification();
  fireEvent.click(screen.getByRole("button", { name: "提交澄清回答" }));

  expect(await screen.findByText(/请求失败：422.*invalid_clarification/)).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: `自定义回答：${proposals[0].question}` })).toHaveValue("由项目管理员负责");
  expect(screen.getByRole("textbox", { name: "需求决策者" })).toHaveValue("需求负责人");
  expect(screen.getByRole("checkbox")).toBeChecked();
  expect(fetcher).toHaveBeenCalledWith("/api/runs/run-1/clarifications/answers", expect.objectContaining({
    body: expect.stringContaining('"custom_answer":"由项目管理员负责"'),
  }));
  expect(screen.getByText("等待用户澄清需求")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "提交澄清回答" })).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByText("等待 PRD 人工审批")).not.toBeInTheDocument());
});

test("submits one PRD section revision and displays only the returned revision", async () => {
  let current = run("prd_awaiting_approval");
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === "/api/health") return json({ status: "ok", service: "speccraft-project-scaffold" });
    if (path === "/api/scaffold") return json(scaffold);
    if (path === "/api/runs/run-1" && !init) return json(current);
    if (path.endsWith("/prd/revisions")) {
      current = {
        ...current,
        prd_draft: { revision: 2, content: "# PRD\n新的验收要求", content_hash: "b".repeat(64) },
        prd_revisions: [...current.prd_revisions, { revision: 2, content: "# PRD\n新的验收要求", content_hash: "b".repeat(64), changed_section_id: "acceptance", feedback: "验收条件更具体" }],
        prd_readiness: { revision: 2, content_hash: "b".repeat(64), issues: [] },
      };
      return json(current);
    }
    return json({ detail: { code: "unexpected" } }, 500);
  });
  installApi(fetcher as typeof fetch);
  render(<App />);

  expect(await screen.findByText("API 已连接")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("textbox", { name: "Run ID" }), { target: { value: "run-1" } });
  fireEvent.click(screen.getByRole("button", { name: "打开 Run" }));
  expect(await screen.findByText("PRD 草稿 · r1")).toBeInTheDocument();
  fireEvent.mouseDown(screen.getByRole("combobox", { name: "修订章节" }));
  fireEvent.click(await screen.findByRole("option", { name: "验收标准" }));
  fireEvent.change(screen.getByRole("textbox", { name: "修订后的章节正文" }), { target: { value: "新的验收要求" } });
  expect(screen.getByRole("textbox", { name: "修订后的章节正文" })).toHaveValue("新的验收要求");
  fireEvent.change(screen.getByRole("textbox", { name: "修订反馈" }), { target: { value: "验收条件更具体" } });
  expect(screen.getByRole("textbox", { name: "修订反馈" })).toHaveValue("验收条件更具体");
  await waitFor(() => expect(screen.getByRole("button", { name: "提交局部修订" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "提交局部修订" }));
  expect(await screen.findByText("PRD 草稿 · r2")).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledWith("/api/runs/run-1/prd/revisions", expect.objectContaining({
    body: JSON.stringify({
      governance_contract_version: 2,
      expected_revision: 1,
      expected_content_hash: "a".repeat(64),
      section_id: "acceptance",
      replacement_body: "新的验收要求",
      feedback: "验收条件更具体",
    }),
  }));
});

test("creates a run from an allowed repository requirement path", async () => {
  const fileRun = run("awaiting_clarification");
  fileRun.source_snapshot = { ...sourceSnapshot, normalized_path: "requirements/large-excel-import.md",
    source: { source_type: "requirement_file", path: "requirements/large-excel-import.md" } };
  fileRun.source_records[0] = { source_id: "source-1", run_id: "run-1", repository_id: "exportflow-sample",
    source_role: "requirement_file", snapshot: fileRun.source_snapshot };
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    if (String(input) === "/api/health") return json({ status: "ok", service: "speccraft-project-scaffold" });
    if (String(input) === "/api/scaffold") return json(scaffold);
    return json(fileRun, 201);
  });
  installApi(fetcher as typeof fetch);
  render(<App />);

  expect(await screen.findByText("API 已连接")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("radio", { name: "仓库内需求文件" }));
  fireEvent.change(screen.getByRole("textbox", { name: "仓库内需求文件路径" }), {
    target: { value: "requirements/large-excel-import.md" },
  });
  fireEvent.click(screen.getByRole("button", { name: "创建 Run" }));

  expect(await screen.findByText("run-1", { selector: ".run-id" })).toBeInTheDocument();
  expect(within(screen.getByRole("group", { name: "来源候选 candidate-1" }))
    .getByText("需求文件 · requirements/large-excel-import.md")).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledWith("/api/runs", expect.objectContaining({
    method: "POST",
    body: JSON.stringify({ governance_contract_version: 2, requirement_path: "requirements/large-excel-import.md" }),
  }));
});

test("opens an existing run by ID and keeps the current run after a read error", async () => {
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const path = String(input);
    if (path === "/api/health") return json({ status: "ok", service: "speccraft-project-scaffold" });
    if (path === "/api/scaffold") return json(scaffold);
    if (path === "/api/runs/run-1") return json(run("prd_awaiting_approval"));
    return json({ detail: { code: "run_not_found" } }, 404);
  });
  installApi(fetcher as typeof fetch);
  render(<App />);

  expect(await screen.findByText("API 已连接")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("textbox", { name: "Run ID" }), { target: { value: "run-1" } });
  fireEvent.click(screen.getByRole("button", { name: "打开 Run" }));
  expect(await screen.findByText("# PRD 问候页面")).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledWith("/api/runs/run-1", undefined);

  fireEvent.change(screen.getByRole("textbox", { name: "Run ID" }), { target: { value: "missing" } });
  fireEvent.click(screen.getByRole("button", { name: "打开 Run" }));
  expect(await screen.findByText(/请求失败：404/)).toBeInTheDocument();
  expect(screen.getByText("# PRD 问候页面")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "批准 PRD" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "提交局部修订" })).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole("textbox", { name: "Run ID" }), { target: { value: "run-1" } });
  fireEvent.click(screen.getByRole("button", { name: "打开 Run" }));
  expect(await screen.findByRole("button", { name: "批准 PRD" })).toBeInTheDocument();
});

test("reads the authoritative Run after a committed workflow checkpoint error", async () => {
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === "/api/health") return json({ status: "ok", service: "speccraft-project-scaffold" });
    if (path === "/api/scaffold") return json(scaffold);
    if (path === "/api/runs" && init?.method === "POST") return json(run("awaiting_clarification"), 201);
    if (path.endsWith("/clarifications/answers")) {
      return json({ detail: { code: "workflow_sync_pending", run_id: "run-1", committed: true } }, 503);
    }
    if (path === "/api/runs/run-1") return json(run("prd_awaiting_approval"));
    return json({ detail: { code: "unexpected" } }, 500);
  });
  installApi(fetcher as typeof fetch);
  render(<App />);

  expect(await screen.findByText("API 已连接")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("一句话需求"), { target: { value: "做一个问候页面" } });
  fireEvent.click(screen.getByRole("button", { name: "创建 Run" }));
  expect(await screen.findByText("等待用户澄清需求")).toBeInTheDocument();
  for (const proposal of proposals) {
    await chooseAnswer(proposal.question, `推荐：${proposal.options[0].label}`);
  }
  await chooseSourceReview("拒绝此来源候选");
  confirmClarification();
  fireEvent.click(screen.getByRole("button", { name: "提交澄清回答" }));

  expect(await screen.findByText("等待 PRD 人工审批")).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledWith("/api/runs/run-1", undefined);
  expect(screen.getByText(/已刷新 Run/)).toBeInTheDocument();
  expect(screen.getByText(/503.*workflow_sync_pending/)).toBeInTheDocument();
  expect(fetcher.mock.calls.filter(([input]) => String(input).endsWith("/clarifications/answers"))).toHaveLength(1);
});

test("keeps the committed warning and hides stale actions if recovery read fails", async () => {
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === "/api/health") return json({ status: "ok", service: "speccraft-project-scaffold" });
    if (path === "/api/scaffold") return json(scaffold);
    if (path === "/api/runs" && init?.method === "POST") return json(run("awaiting_clarification"), 201);
    if (path.endsWith("/clarifications/answers")) {
      return json({ detail: { code: "workflow_sync_pending", run_id: "run-1", committed: true } }, 503);
    }
    if (path === "/api/runs/run-1") return json({ detail: { code: "unavailable" } }, 503);
    return json({ detail: { code: "unexpected" } }, 500);
  });
  installApi(fetcher as typeof fetch);
  render(<App />);

  expect(await screen.findByText("API 已连接")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("一句话需求"), { target: { value: "做一个问候页面" } });
  fireEvent.click(screen.getByRole("button", { name: "创建 Run" }));
  expect(await screen.findByText("等待用户澄清需求")).toBeInTheDocument();
  for (const proposal of proposals) {
    await chooseAnswer(proposal.question, `推荐：${proposal.options[0].label}`);
  }
  await chooseSourceReview("拒绝此来源候选");
  confirmClarification();
  fireEvent.click(screen.getByRole("button", { name: "提交澄清回答" }));

  expect(await screen.findByText(/命令已保存.*run-1/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "提交澄清回答" })).not.toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Run ID" })).toHaveValue("run-1");
  expect(screen.getByText(/503.*workflow_sync_pending/)).toBeInTheDocument();
  expect(fetcher.mock.calls.filter(([input]) => String(input).endsWith("/clarifications/answers"))).toHaveLength(1);
});

function clarificationApi() {
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === "/api/health") return json({ status: "ok", service: "speccraft-project-scaffold" });
    if (path === "/api/scaffold") return json(scaffold);
    if (path.endsWith("/clarifications/answers")) return json({ detail: { code: "source_conflict" } }, 409);
    if (path === "/api/runs" && init?.method === "POST") return json(run("awaiting_clarification"), 201);
    return json({ detail: { code: "unexpected" } }, 500);
  });
  installApi(fetcher as typeof fetch);
  return fetcher;
}

async function createRunInUi() {
  render(<App />);
  expect(await screen.findByText("API 已连接")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("一句话需求"), { target: { value: "做一个问候页面" } });
  fireEvent.click(screen.getByRole("button", { name: "创建 Run" }));
  expect(await screen.findByText("等待用户澄清需求")).toBeInTheDocument();
}

test("starts with an empty Ledger and requires each source review and explicit user confirmation", async () => {
  const fetcher = clarificationApi();
  await createRunInUi();
  expect(screen.getByText("尚无已确认 FACT 或 DECISION")).toBeInTheDocument();
  const sourceGroup = screen.getByRole("group", { name: "来源候选 candidate-1" });
  expect(within(sourceGroup).getByText("内联需求 · 用户内联输入")).toBeInTheDocument();
  expect(within(sourceGroup).getByText(`SHA-256 ${"a".repeat(64)}`)).toBeInTheDocument();
  expect(within(sourceGroup).getByText("做一个问候页面")).toBeInTheDocument();
  expect(within(sourceGroup).getByText("请选择来源用途或拒绝")).toBeInTheDocument();
  expect(screen.getByRole("checkbox")).not.toBeChecked();
  for (const proposal of proposals) await chooseAnswer(proposal.question, `推荐：${proposal.options[0].label}`);
  confirmClarification();
  const submit = screen.getByRole("button", { name: "提交澄清回答" });
  expect(submit).toBeDisabled();
  fireEvent.click(submit);
  expect(fetcher.mock.calls.filter(([input]) => String(input).endsWith("/clarifications/answers"))).toHaveLength(0);
  await chooseSourceReview("拒绝此来源候选");
  expect(submit).toBeEnabled();
  fireEvent.click(screen.getByRole("checkbox"));
  expect(submit).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.change(screen.getByRole("textbox", { name: "需求决策者" }), { target: { value: "  " } });
  expect(submit).toBeDisabled();
  fireEvent.change(screen.getByRole("textbox", { name: "需求决策者" }), { target: { value: "需求负责人" } });
  fireEvent.change(screen.getByRole("textbox", { name: "需求决策理由" }), { target: { value: "  " } });
  expect(submit).toBeDisabled();
});

test("rejects sources and submits all five explicit decisions with precise v2 review identity", async () => {
  const fetcher = clarificationApi();
  await createRunInUi();
  await chooseSourceReview("拒绝此来源候选");
  for (const proposal of proposals) await chooseAnswer(proposal.question, `推荐：${proposal.options[0].label}`);
  confirmClarification();
  fireEvent.click(screen.getByRole("button", { name: "提交澄清回答" }));
  expect(await screen.findByText(/请求失败：409.*source_conflict/)).toBeInTheDocument();
  const request = fetcher.mock.calls.find(([input]) => String(input).endsWith("/clarifications/answers"));
  const body = JSON.parse(String(request?.[1]?.body));
  expect(body).toEqual({
    governance_contract_version: 2, expected_revision: 1, batch_id: "batch-1", batch_revision: 1,
    command_id: expect.any(String), actor_claim: "需求负责人", rationale: "逐项审阅", user_confirmed: true,
    source_reviews: [{ review_id: expect.any(String), candidate_id: "candidate-1", candidate_revision: 1,
      source_id: "source-1", source_sha256: "a".repeat(64), action: "reject" }],
    answers: proposals.map((proposal) => ({ question_id: proposal.question_id, selected_option_id: proposal.options[0].option_id })),
  });
  expect(screen.getByText("等待用户澄清需求")).toBeInTheDocument();
  expect(screen.queryByText("PRD 草稿 · r1")).not.toBeInTheDocument();
});

test("offers a source reference only for its explicitly accepted product dimension and invalidates changed usage", async () => {
  const fetcher = clarificationApi();
  await createRunInUi();
  await chooseSourceReview("接受为产品事实：角色");
  await chooseAnswer(proposals[0].question, "引用来源候选 candidate-1：做一个问候页面");
  for (const proposal of proposals.slice(1)) {
    const group = screen.getByRole("group", { name: proposal.question });
    fireEvent.mouseDown(within(group).getByRole("combobox"));
    await waitFor(() => expect(screen.queryByRole("option", { name: /引用来源候选/ })).not.toBeInTheDocument());
    fireEvent.click(await screen.findByRole("option", { name: `推荐：${proposal.options[0].label}` }));
  }
  confirmClarification();
  expect(screen.getByRole("button", { name: "提交澄清回答" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "提交澄清回答" }));
  expect(await screen.findByText(/source_conflict/)).toBeInTheDocument();
  const request = fetcher.mock.calls.find(([input]) => String(input).endsWith("/clarifications/answers"));
  const body = JSON.parse(String(request?.[1]?.body));
  expect(body.source_reviews[0]).toMatchObject({ action: "accept", usage: "product", dimension: "role" });
  expect(body.answers[0]).toEqual({ question_id: proposals[0].question_id, confirmed_candidate_id: "candidate-1" });
  await chooseSourceReview("接受为背景资料");
  expect(screen.getByRole("button", { name: "提交澄清回答" })).toBeDisabled();
  const roleGroup = screen.getByRole("group", { name: proposals[0].question });
  fireEvent.mouseDown(within(roleGroup).getByRole("combobox"));
  await waitFor(() => expect(screen.queryByRole("option", { name: /引用来源候选/ })).not.toBeInTheDocument());
  fireEvent.click(await screen.findByRole("option", { name: `推荐：${proposals[0].options[0].label}` }));
  fireEvent.click(screen.getByRole("button", { name: "提交澄清回答" }));
  await waitFor(() => expect(fetcher.mock.calls.filter(([input]) => String(input).endsWith("/clarifications/answers"))).toHaveLength(2));
  const last = fetcher.mock.calls.filter(([input]) => String(input).endsWith("/clarifications/answers")).at(-1);
  expect(JSON.parse(String(last?.[1]?.body)).source_reviews[0]).toMatchObject({ action: "accept", usage: "background_only", dimension: null });
});

test("validates trimmed requirement emptiness while preserving the exact submitted source text", async () => {
  const fetcher = clarificationApi();
  render(<App />);
  expect(await screen.findByText("API 已连接")).toBeInTheDocument();
  const input = screen.getByLabelText("一句话需求");
  fireEvent.change(input, { target: { value: " \n " } });
  expect(screen.getByRole("button", { name: "创建 Run" })).toBeDisabled();
  const raw = "  做一个问候页面\n";
  fireEvent.change(input, { target: { value: raw } });
  fireEvent.click(screen.getByRole("button", { name: "创建 Run" }));
  expect(await screen.findByText("等待用户澄清需求")).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledWith("/api/runs", expect.objectContaining({
    body: JSON.stringify({ governance_contract_version: 2, requirement: raw }),
  }));
});

test("submits an explicit technical decision with governance version 2", async () => {
  const current = { ...run("prd_awaiting_approval"), status: "td_awaiting_decision",
    available_commands: ["submit_technical_decisions"],
    technical_decision_requests: [{ request_id: "api-choice", topic: "api", question: "选择 API 形式", options: ["HTTP API"], reason: "待确认接口" }] };
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === "/api/health") return json({ status: "ok", service: "speccraft-project-scaffold" });
    if (path === "/api/scaffold") return json(scaffold);
    if (path.endsWith("/technical-decisions")) return json(run("td_awaiting_approval"));
    if (path === "/api/runs/run-1" && !init) return json(current);
    return json({ detail: { code: "unexpected" } }, 500);
  });
  installApi(fetcher as typeof fetch);
  render(<App />);
  expect(await screen.findByText("API 已连接")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("textbox", { name: "Run ID" }), { target: { value: "run-1" } });
  fireEvent.click(screen.getByRole("button", { name: "打开 Run" }));
  expect(await screen.findByText("等待技术决定")).toBeInTheDocument();
  fireEvent.mouseDown(screen.getByRole("combobox", { name: "选择 API 形式" }));
  fireEvent.click(await screen.findByRole("option", { name: "HTTP API" }));
  fireEvent.change(screen.getByRole("textbox", { name: "技术决策人" }), { target: { value: "技术负责人" } });
  fireEvent.click(screen.getByRole("button", { name: "提交技术决定" }));
  expect(await screen.findByText("等待 TD 人工审批")).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledWith("/api/runs/run-1/technical-decisions", expect.objectContaining({
    body: JSON.stringify({ governance_contract_version: 2, expected_prd_revision: 1, expected_prd_content_hash: "a".repeat(64),
      decisions: [{ request_id: "api-choice", answer: "HTTP API", actor: "技术负责人" }] }),
  }));
});
