import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import App from "./App";

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

function run(status: string) {
  const awaiting = status === "awaiting_clarification";
  const base = {
    run_id: "run-1",
    requirement: "做一个问候页面",
    status,
    prd_blueprint: awaiting ? null : { sections: [{ section_id: "acceptance", title: "验收标准", applicable: true, fact_ids: [] }] },
    prd_revisions: awaiting ? [] : [{ revision: 1, content: "# PRD\n问候页面", content_hash: "a".repeat(64) }],
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
        ? [{ fact_id: "source-1", kind: "fact", dimension: null, claim: "做一个问候页面" }]
        : [
          { fact_id: "source-1", kind: "fact", dimension: null, claim: "做一个问候页面" },
          ...proposals.map((proposal) => ({
            fact_id: `decision-${proposal.gap_id}`,
            kind: "decision",
            dimension: proposal.gap_id.slice(4),
            claim: proposal.options[0].label,
          })),
        ],
    },
    completeness: {
      ledger_revision: awaiting ? 1 : 2,
      is_complete: !awaiting,
      gaps: awaiting ? proposals.map((proposal) => ({
        gap_id: proposal.gap_id,
        dimension: proposal.gap_id.slice(4),
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
    } : null,
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
    body: JSON.stringify({ requirement: "做一个问候页面" }),
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
  expect(submitAnswers).toBeEnabled();
  fireEvent.click(submitAnswers);
  expect(await screen.findByText("等待 PRD 人工审批")).toBeInTheDocument();
  expect(screen.getByText("# PRD 问候页面")).toBeInTheDocument();
  const answerCall = fetcher.mock.calls.find(([input]) => String(input).endsWith("/clarifications/answers"));
  expect(answerCall?.[1]).toEqual(expect.objectContaining({
    method: "POST",
    body: expect.stringContaining('"command_id":"run-1:clarification:1"'),
  }));

  fireEvent.change(screen.getByRole("textbox", { name: "审批人" }), { target: { value: "审阅人" } });
  fireEvent.change(screen.getByRole("textbox", { name: "审批理由" }), { target: { value: "同意当前版本" } });
  fireEvent.click(screen.getByRole("button", { name: "批准 PRD" }));
  expect(await screen.findByText("等待 TD 人工审批")).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledWith("/api/runs/run-1/approvals/prd", expect.objectContaining({
    body: JSON.stringify({ revision: 1, content_hash: "a".repeat(64), actor: "审阅人", rationale: "同意当前版本" }),
  }));
  expect(screen.getByText("# TD 使用 React")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("textbox", { name: "TD 审批人" }), { target: { value: "技术审阅人" } });
  fireEvent.change(screen.getByRole("textbox", { name: "TD 审批理由" }), { target: { value: "同意当前技术方案" } });
  fireEvent.click(screen.getByRole("button", { name: "批准 TD" }));
  expect(await screen.findByText("已完成")).toBeInTheDocument();
  expect(screen.getByText(/\"schema_version\": \"1.0\"/)).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledWith("/api/runs/run-1/approvals/td", expect.objectContaining({
    method: "POST",
    body: JSON.stringify({ revision: 1, content_hash: "d".repeat(64), actor: "技术审阅人", rationale: "同意当前技术方案" }),
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
  fireEvent.click(screen.getByRole("button", { name: "提交澄清回答" }));

  expect(await screen.findByText(/请求失败：422/)).toBeInTheDocument();
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
        prd_revisions: [...current.prd_revisions, { revision: 2, content: "# PRD\n新的验收要求", content_hash: "b".repeat(64) }],
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
  fireEvent.change(screen.getByRole("combobox", { name: "修订章节" }), { target: { value: "acceptance" } });
  expect(screen.getByRole("combobox", { name: "修订章节" })).toHaveValue("acceptance");
  fireEvent.change(screen.getByRole("textbox", { name: "修订后的章节正文" }), { target: { value: "新的验收要求" } });
  expect(screen.getByRole("textbox", { name: "修订后的章节正文" })).toHaveValue("新的验收要求");
  fireEvent.change(screen.getByRole("textbox", { name: "修订反馈" }), { target: { value: "验收条件更具体" } });
  expect(screen.getByRole("textbox", { name: "修订反馈" })).toHaveValue("验收条件更具体");
  await waitFor(() => expect(screen.getByRole("button", { name: "提交局部修订" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "提交局部修订" }));
  expect(await screen.findByText("PRD 草稿 · r2")).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledWith("/api/runs/run-1/prd/revisions", expect.objectContaining({
    body: JSON.stringify({
      expected_revision: 1,
      expected_content_hash: "a".repeat(64),
      section_id: "acceptance",
      replacement_body: "新的验收要求",
      feedback: "验收条件更具体",
    }),
  }));
});

test("creates a run from an allowed repository requirement path", async () => {
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    if (String(input) === "/api/health") return json({ status: "ok", service: "speccraft-project-scaffold" });
    if (String(input) === "/api/scaffold") return json(scaffold);
    return json(run("awaiting_clarification"), 201);
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
  expect(fetcher).toHaveBeenCalledWith("/api/runs", expect.objectContaining({
    method: "POST",
    body: JSON.stringify({ requirement_path: "requirements/large-excel-import.md" }),
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
});
