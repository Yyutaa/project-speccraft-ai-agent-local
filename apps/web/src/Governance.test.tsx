import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import App from "./App";
import type { Run } from "./api";

const hash = "a".repeat(64);
const snapshot = { source: { source_type: "inline_requirement", path: null }, normalized_path: null, sha256: hash, read_status: "read", content: "需求原文" };
const reference = { kind: "candidate", reference_id: "candidate-1", source_id: "source-1", source_sha256: hash, start: 0, end: 4, excerpt: "需求原文" };
const assumption = { assumption_id: "assumption-1", client_ref: "a1", revision: 3, statement: "允许管理员导出", affected_dimensions: ["permission"], risk: "high", product_impact: "present", basis_refs: [reference], status: "pending", producer_kind: "user", supersedes_id: null };
const dimension = { question_id: "q-permission", target_kind: "dimension", target_id: null, object_revision: null, gap_id: "gap-permission", question: "最终权限是什么？", options: [{ option_id: "admin", label: "仅管理员导出" }], recommended_option_id: "admin", recommendation_reason: "需要用户确认" };
const assumptionQuestion = { ...dimension, question_id: "q-assumption", target_kind: "assumption", target_id: "assumption-1", object_revision: 3, gap_id: "gap-assumption", question: "如何处理此假设？" };
function run(extra = {}) {
  return { governance_contract_version: 2, run_id: "run-1", parent_run_id: null, requirement: "需求原文", status: "awaiting_clarification", available_commands: ["submit_clarification"],
    prd_blueprint: null, prd_revisions: [], prd_draft: null, prd_readiness: null, prd_approval: null, design_authority: null, td_blueprint: null, td_draft: null, td_revisions: [], td_readiness: null, td_review: null, td_review_records: [], td_approval: null, delivery_spec: null, artifact_envelopes: [], technical_decision_requests: [], technical_decisions: [],
    source_snapshot: snapshot, source_records: [], pending_source_claims: [], source_admission_evidence: [], repository_binding: { repository_id: "sample", permission: "read_only", context_mode: "guide_only" }, harness_context: { entries: [], sha256: hash }, ledger: { revision: 4, facts: [] }, completeness: { ledger_revision: 4, gaps: [{ gap_id: "gap-permission", dimension: "permission", blocking: true }, { gap_id: "gap-assumption", dimension: "permission", blocking: true }] },
    clarification_batch: { batch_id: "batch-1", revision: 2, ledger_revision: 4, gap_ids: ["gap-permission", "gap-assumption"], blocking_gap_ids: ["gap-permission", "gap-assumption"], required_candidate_ids: [], proposals: [dimension, assumptionQuestion] },
    prd_supporting_context: { knowledge_citations: [], assumptions: [] }, knowledge_citations: [], assumptions: [assumption], context_conflicts: [], assumption_resolution_evidence: [], context_resolution_evidence: [], ...extra };
}
const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
function setup(current: unknown = run(), response?: (path: string, init?: RequestInit) => Promise<Response>) {
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === "/api/health") return json({ status: "ok" });
    if (path === "/api/scaffold") return json({ stages: [], implemented_capabilities: [], deferred_capabilities: [] });
    if (init?.method === "POST") return response?.(path, init) ?? json({ detail: { code: "invalid_request" } }, 422);
    return json(current);
  });
  vi.stubGlobal("fetch", fetcher);
  render(<App />);
  return fetcher;
}
async function open() {
  await screen.findByText("API 已连接");
  fireEvent.change(screen.getByRole("textbox", { name: "Run ID" }), { target: { value: "run-1" } });
  fireEvent.click(screen.getByRole("button", { name: "打开 Run" }));
  await screen.findByRole("article", { name: "需求澄清" });
}
async function select(label: string, option: string) {
  fireEvent.mouseDown(screen.getByRole("combobox", { name: label }));
  fireEvent.click(await screen.findByRole("option", { name: option }));
}
function fill(label: string, value: string) { fireEvent.change(screen.getByRole("textbox", { name: label }), { target: { value } }); }
function confirm() {
  fill("需求决策者", "产品负责人"); fill("需求决策理由", "核对当前版本");
  fireEvent.click(screen.getByRole("checkbox", { name: "我确认这是本人明确提交的来源处理与需求决定" }));
}
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

test("creates structured knowledge, assumptions, conflict references and parent without safe defaults; retains failed inputs", async () => {
  const fetcher = setup();
  await screen.findByText("API 已连接");
  fill("一句话需求", "需求原文"); fill("父 Run ID（可选）", "parent-1");
  fireEvent.click(screen.getByRole("button", { name: "添加知识引用" }));
  fill("知识引用 1 别名", "k1"); fill("知识引用 1 路径", "knowledge/policy.md");
  fireEvent.change(screen.getByRole("spinbutton", { name: "知识引用 1 起点" }), { target: { value: "0" } });
  fireEvent.change(screen.getByRole("spinbutton", { name: "知识引用 1 终点" }), { target: { value: "4" } });
  fill("知识引用 1 用途", "核对限制");
  fireEvent.click(screen.getByRole("button", { name: "添加假设" }));
  fill("假设 1 别名", "a1"); fill("假设 1 陈述", "允许管理员导出");
  expect(screen.getByRole("combobox", { name: "假设 1 风险" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "添加上下文冲突" }));
  fill("冲突 1 别名", "c1"); fill("冲突 1 右侧引用别名", "k1");
  await select("冲突 1 右侧引用类型", "知识引用");
  fill("冲突 1 理由", "两份资料约束不同");
  fireEvent.click(screen.getByRole("button", { name: "创建 Run" }));
  expect(await screen.findByText(/422.*invalid_request/)).toBeInTheDocument();
  const body = JSON.parse(String(fetcher.mock.calls.find(([p, init]) => p === "/api/runs" && init?.method === "POST")?.[1]?.body));
  expect(body).toMatchObject({ governance_contract_version: 2, parent_run_id: "parent-1", knowledge_selections: [{ client_ref: "k1", path: "knowledge/policy.md", start: 0, end: 4, purpose: "核对限制" }], assumptions: [{ client_ref: "a1", statement: "允许管理员导出", risk: "unknown", product_impact: "unknown", basis_refs: [{ kind: "candidate", client_ref: "requirement_candidate" }] }], context_conflicts: [{ client_ref: "c1", left_ref: { kind: "candidate", client_ref: "requirement_candidate" }, right_ref: { kind: "citation", client_ref: "k1" }, reason: "两份资料约束不同" }] });
  expect(screen.getByRole("textbox", { name: "假设 1 陈述" })).toHaveValue("允许管理员导出");
  fill("假设 1 别名", "k1");
  expect(screen.getByRole("button", { name: "创建 Run" })).toBeDisabled();
  expect(screen.getByText(/别名必须唯一/)).toBeInTheDocument();
});

test("requires explicit assumption resolution and dimension answer, uses bound identity and preserves failures", async () => {
  const fetcher = setup(); await open();
  expect(screen.getByRole("button", { name: "提交澄清回答" })).toBeDisabled();
  await select("最终权限是什么？", "推荐：仅管理员导出");
  await select("假设处理：如何处理此假设？", "接受假设");
  fill("假设处理理由：如何处理此假设？", "以最终权限为准"); confirm();
  expect(screen.getByRole("button", { name: "提交澄清回答" })).toBeDisabled();
  await select("假设关联最终答案：如何处理此假设？", "权限：最终权限是什么？");
  fireEvent.click(screen.getByRole("button", { name: "提交澄清回答" }));
  await screen.findByText(/422.*invalid_request/);
  const body = JSON.parse(String(fetcher.mock.calls.find(([p]) => String(p).endsWith("clarifications/answers"))?.[1]?.body));
  expect(body.answers).toEqual([{ question_id: "q-permission", selected_option_id: "admin" }]);
  expect(body.assumption_resolutions).toEqual([{ question_id: "q-assumption", assumption_id: "assumption-1", expected_assumption_revision: 3, action: "accept", rationale: "以最终权限为准", final_answer_question_ids: ["q-permission"] }]);
  expect(screen.getByRole("textbox", { name: "假设处理理由：如何处理此假设？" })).toHaveValue("以最终权限为准");
});

test("shows low risk pending reference without requiring a resolution", async () => {
  setup(run({ assumptions: [{ ...assumption, affected_dimensions: [], risk: "low", product_impact: "none" }], clarification_batch: { batch_id: "batch-1", revision: 2, required_candidate_ids: [], blocking_gap_ids: ["gap-permission"], proposals: [dimension] } }));
  await open(); await select("最终权限是什么？", "推荐：仅管理员导出"); confirm();
  expect(screen.getByText(/未确认假设与处理历史/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "提交澄清回答" })).toBeEnabled();
});

test("requires conflict resolution reason and bound dimension answer or explicit exclusion", async () => {
  const conflict = { conflict_id: "conflict-1", client_ref: "c1", revision: 2, dimension: null, status: "pending", reason: "资料冲突", discoverer_kind: "user", left_ref: reference, right_ref: { ...reference, reference_id: "citation-1", kind: "citation", excerpt: "禁止导出" } };
  const question = { ...assumptionQuestion, question_id: "q-conflict", target_kind: "context_conflict", target_id: "conflict-1", object_revision: 2, question: "如何处理冲突？" };
  const fetcher = setup(run({ assumptions: [], context_conflicts: [conflict], clarification_batch: { batch_id: "batch-1", revision: 2, required_candidate_ids: [], blocking_gap_ids: [dimension.gap_id, question.gap_id], proposals: [dimension, question] } }));
  await open(); await select("最终权限是什么？", "推荐：仅管理员导出"); confirm();
  await select("冲突处理：如何处理冲突？", "排除一侧引用");
  expect(screen.getByRole("button", { name: "提交澄清回答" })).toBeDisabled();
  fill("冲突处理理由：如何处理冲突？", "知识已过期");
  await select("排除引用：如何处理冲突？", "右侧：禁止导出");
  fireEvent.click(screen.getByRole("button", { name: "提交澄清回答" }));
  await screen.findByText(/invalid_request/);
  const body = JSON.parse(String(fetcher.mock.calls.find(([p]) => String(p).endsWith("clarifications/answers"))?.[1]?.body));
  expect(body.context_conflict_resolutions).toEqual([{ question_id: "q-conflict", conflict_id: "conflict-1", expected_conflict_revision: 2, action: "exclude", rationale: "知识已过期", excluded_reference_id: "citation-1" }]);
});

const binding = { run_id: "run-1", prd_revision: 1, prd_content_hash: hash, td_revision: 1, td_content_hash: "b".repeat(64), authority_pack_hash: "c".repeat(64), obligations_hash: "d".repeat(64) };
const finding = { finding_id: "finding-1", producer_kind: "human", category: "product_conflict", obligation_ids: ["obligation-1"], prd_excerpt: { start: 0, end: 5, excerpt: "😀仅管理员" }, td_excerpt: { start: 0, end: 5, excerpt: "访客可导出" }, reason: "权限冲突", disposition: "confirmed_conflict", disposition_rationale: "核对权限" };
function tdRun(extra = {}): Run {
  return run({ status: "td_awaiting_approval", available_commands: ["record_td_review", "revise_td"], clarification_batch: null,
    prd_draft: { revision: 1, content_hash: hash, content: "😀仅管理员导出" },
    td_draft: { revision: 1, content_hash: binding.td_content_hash, content: "访客可导出", prd_revision: 1, prd_content_hash: hash, authority_pack_hash: binding.authority_pack_hash, obligations: [{ obligation_id: "obligation-1", statement: "仅管理员", prd_section_id: "permission", prd_section_hash: hash, source_fact_ids: [] }] },
    td_blueprint: { sections: [{ section_id: "frontend", title: "前端页面、组件、交互与状态管理", authority_ids: [], obligation_ids: ["obligation-1"] }], obligation_ids: ["obligation-1"] },
    td_review: { binding, status: "missing", current_review_id: null, review_revision: 0, blocking_finding_ids: [] }, td_readiness: { revision: 1, content_hash: binding.td_content_hash, ready: true, issues: [] }, ...extra }) as unknown as Run;
}
async function openTd() {
  await screen.findByText("API 已连接"); fill("Run ID", "run-1"); fireEvent.click(screen.getByRole("button", { name: "打开 Run" }));
  await screen.findByRole("heading", { name: "TD 草稿 · r1" });
}
function reviewIdentity() {
  fill("TD 审阅人", "技术负责人"); fill("TD 审阅理由", "逐项检查义务与正文");
  fireEvent.click(screen.getByRole("checkbox", { name: "我已逐项核对全部冻结义务，并明确提交本次人工审阅" }));
}
function lastBody(fetcher: ReturnType<typeof setup>, ending: string) {
  return JSON.parse(String(fetcher.mock.calls.filter(([p]) => String(p).endsWith(ending)).at(-1)?.[1]?.body));
}

test("records a deliberate no-conflict report with exact server binding and never exposes an unoffered approval", async () => {
  const fetcher = setup(tdRun()); await openTd();
  expect(screen.queryByRole("button", { name: "批准 TD" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "提交 TD 人工审阅" })).toBeDisabled();
  expect(screen.getByRole("checkbox", { name: /逐项核对全部冻结义务/ })).not.toBeChecked();
  reviewIdentity(); expect(screen.getByRole("button", { name: "提交 TD 人工审阅" })).toBeDisabled();
  await select("TD 人工审阅结论", "未观察到冲突");
  fireEvent.click(screen.getByRole("button", { name: "提交 TD 人工审阅" }));
  await screen.findByText(/422.*invalid_request/);
  expect(lastBody(fetcher, "/td/reviews")).toEqual({ governance_contract_version: 2, command_id: expect.any(String), expected_review_revision: 0, prior_review_id: null, binding, producer_kind: "human", actor_claim: "技术负责人", rationale: "逐项检查义务与正文", user_confirmed: true, human_conclusion: "no_conflict_observed", reviewed_obligation_ids: ["obligation-1"], findings: [], existing_finding_dispositions: [], rechecks: [] });
  expect(screen.getByRole("textbox", { name: "TD 审阅理由" })).toHaveValue("逐项检查义务与正文");
});

test("adds a human finding only with exact codepoint excerpts and explicit disposition", async () => {
  const fetcher = setup(tdRun()); await openTd(); reviewIdentity();
  fireEvent.click(screen.getByRole("button", { name: "添加 TD 发现" }));
  await select("新发现 1 类型", "产品冲突"); await select("新发现 1 关联义务", "obligation-1：仅管理员");
  fill("新发现 1 PRD 精确摘录", "😀仅管理员");
  fireEvent.change(screen.getByRole("spinbutton", { name: "新发现 1 PRD 终点" }), { target: { value: "6" } });
  fill("新发现 1 TD 精确摘录", "访客可导出");
  fireEvent.change(screen.getByRole("spinbutton", { name: "新发现 1 TD 终点" }), { target: { value: "5" } });
  fill("新发现 1 理由", "权限冲突"); await select("新发现 1 裁决", "确认冲突");
  await select("TD 人工审阅结论", "需要修订技术方案");
  expect(screen.getByRole("button", { name: "提交 TD 人工审阅" })).toBeDisabled();
  fireEvent.change(screen.getByRole("spinbutton", { name: "新发现 1 PRD 终点" }), { target: { value: "5" } });
  fireEvent.click(screen.getByRole("button", { name: "提交 TD 人工审阅" })); await screen.findByText(/invalid_request/);
  const body = lastBody(fetcher, "/td/reviews");
  expect(body.findings).toEqual([expect.objectContaining({ producer_kind: "human", category: "product_conflict", obligation_ids: ["obligation-1"], prd_excerpt: { start: 0, end: 5, excerpt: "😀仅管理员" }, td_excerpt: { start: 0, end: 5, excerpt: "访客可导出" }, reason: "权限冲突", disposition: "confirmed_conflict" })]);
});

function reviewedRun(stale = false) {
  const currentBinding = stale ? { ...binding, td_revision: 2, td_content_hash: "e".repeat(64) } : binding;
  const base = tdRun();
  return tdRun({ td_draft: { ...base.td_draft, revision: stale ? 2 : 1, content_hash: currentBinding.td_content_hash, content: stale ? "访客仍可导出" : "访客可导出" },
    td_review: { binding: currentBinding, status: stale ? "stale" : "blocked", current_review_id: "server-review-1", review_revision: stale ? 2 : 1, blocking_finding_ids: ["finding-1"] },
    td_review_records: [{ review_id: "server-review-1", review_revision: 1, binding, findings: [structuredClone(finding)], human_conclusion: "changes_required", computed_status: "blocked", reviewed_obligation_ids: ["obligation-1"], prior_review_id: null, actor_claim: "原审阅人", rationale: "原理由", reviewed_at: "2026-10-29T00:00:00Z", rechecks: [] }] });
}

test("requires an explicit justified disposition for old findings and never resends them as new", async () => {
  const fetcher = setup(reviewedRun()); await openTd(); reviewIdentity();
  await select("TD 人工审阅结论", "未观察到冲突");
  expect(screen.getByRole("button", { name: "提交 TD 人工审阅" })).toBeDisabled();
  await select("发现 finding-1 本次裁决", "有理由的误报");
  expect(screen.getByRole("button", { name: "提交 TD 人工审阅" })).toBeDisabled();
  fill("发现 finding-1 裁决理由", "明确核对后撤回误报");
  fireEvent.click(screen.getByRole("button", { name: "提交 TD 人工审阅" })); await screen.findByText(/invalid_request/);
  expect(lastBody(fetcher, "/td/reviews")).toMatchObject({ prior_review_id: "server-review-1", expected_review_revision: 1, findings: [], existing_finding_dispositions: [{ finding_id: "finding-1", disposition: "dismissed", disposition_rationale: "明确核对后撤回误报" }], rechecks: [] });
});

test.each(["fixed", "still_present", "not_applicable"])("requires every stale finding recheck: %s retains old evidence", async (outcome) => {
  const fetcher = setup(reviewedRun(true));
  await screen.findByText("API 已连接"); fill("Run ID", "run-1"); fireEvent.click(screen.getByRole("button", { name: "打开 Run" })); await screen.findByRole("heading", { name: "TD 草稿 · r2" });
  reviewIdentity(); await select("TD 人工审阅结论", outcome === "still_present" ? "需要修订技术方案" : "未观察到冲突");
  expect(screen.getByRole("button", { name: "提交 TD 人工审阅" })).toBeDisabled();
  await select("发现 finding-1 复查结果", ({ fixed: "已修复", still_present: "仍然存在", not_applicable: "不再适用" })[outcome]!);
  fill("发现 finding-1 复查理由", "逐项核对新版本");
  if (outcome === "still_present") {
    expect(screen.getByRole("button", { name: "提交 TD 人工审阅" })).toBeDisabled();
    fill("发现 finding-1 新 TD 精确摘录", "访客仍可导出");
    fireEvent.change(screen.getByRole("spinbutton", { name: "发现 finding-1 新 TD 终点" }), { target: { value: "6" } });
  }
  fireEvent.click(screen.getByRole("button", { name: "提交 TD 人工审阅" })); await screen.findByText(/invalid_request/);
  const body = lastBody(fetcher, "/td/reviews");
  expect(body.findings).toEqual([]); expect(body.existing_finding_dispositions).toEqual([]);
  expect(body.rechecks).toEqual([{ finding_id: "finding-1", outcome, rationale: "逐项核对新版本", ...(outcome === "still_present" ? { td_excerpt: { start: 0, end: 6, excerpt: "访客仍可导出" } } : {}) }]);
  expect(body.binding.td_revision).toBe(2); expect(body.expected_review_revision).toBe(2);
  expect(screen.getAllByText(/访客可导出/).length).toBeGreaterThan(0);
});

test("submits one TD canonical section with current versions and shows only returned stale projection", async () => {
  const current = tdRun();
  const fetcher = setup(current, (path) => path.endsWith("/td/revisions") ? json(reviewedRun(true)) : json({ detail: { code: "invalid_request" } }, 422));
  await openTd();
  await select("TD 修订章节", "前端页面、组件、交互与状态管理"); fill("TD 修订后的章节正文", "仅管理员可导出"); fill("TD 修订反馈", "恢复批准的权限"); fill("TD 修订人", "技术负责人");
  fireEvent.click(screen.getByRole("button", { name: "提交 TD 单章修订" }));
  await screen.findByRole("heading", { name: "TD 草稿 · r2" });
  expect(lastBody(fetcher, "/td/revisions")).toEqual({ governance_contract_version: 2, command_id: expect.any(String), section_id: "frontend", replacement_body: "仅管理员可导出", feedback: "恢复批准的权限", actor_claim: "技术负责人", expected_td_revision: 1, expected_td_content_hash: binding.td_content_hash, expected_review_revision: 0 });
  expect(screen.getByText(/当前 TD 审阅.*stale/)).toBeInTheDocument(); expect(screen.queryByRole("button", { name: "批准 TD" })).not.toBeInTheDocument();
});

test("requires explicit accept or reject after revising assumption values and sends only revision fields", async () => {
  const fetcher = setup(); await open();
  await select("最终权限是什么？", "推荐：仅管理员导出"); confirm();
  await select("假设处理：如何处理此假设？", "修订假设");
  fill("修订假设：如何处理此假设？ 陈述", "资料只是背景，不改变权限");
  await select("修订假设：如何处理此假设？ 产品影响", "无产品影响");
  await select("修订假设：如何处理此假设？ 风险", "低风险");
  fill("假设处理理由：如何处理此假设？", "撤回原产品假设");
  expect(screen.getByRole("button", { name: "提交澄清回答" })).toBeDisabled();
  await select("修订后处理：如何处理此假设？", "拒绝修订后的假设");
  fireEvent.click(screen.getByRole("button", { name: "提交澄清回答" })); await screen.findByText(/invalid_request/);
  expect(lastBody(fetcher, "/clarifications/answers").assumption_resolutions).toEqual([{ question_id: "q-assumption", assumption_id: "assumption-1", expected_assumption_revision: 3, action: "revise", rationale: "撤回原产品假设", final_answer_question_ids: [], revised_action: "reject", revised_assumption: { statement: "资料只是背景，不改变权限", affected_dimensions: ["permission"], risk: "low", product_impact: "none" } }]);
});

test("requires a product conflict to link an explicit dimension decision and cannot exclude product obligations", async () => {
  const conflict = { conflict_id: "conflict-1", revision: 2, dimension: "permission", status: "pending", reason: "权限冲突", left_ref: reference, right_ref: { ...reference, reference_id: "citation-1", kind: "citation", excerpt: "禁止导出" } };
  const question = { ...assumptionQuestion, question_id: "q-conflict", target_kind: "context_conflict", target_id: "conflict-1", object_revision: 2, question: "如何处理产品冲突？" };
  const fetcher = setup(run({ assumptions: [], context_conflicts: [conflict], clarification_batch: { batch_id: "batch-1", revision: 2, required_candidate_ids: [], blocking_gap_ids: [dimension.gap_id, question.gap_id], proposals: [dimension, question] } }));
  await open(); confirm(); await select("冲突处理：如何处理产品冲突？", "关联最终维度答案");
  fill("冲突处理理由：如何处理产品冲突？", "由用户确定权限");
  await select("冲突关联最终答案：如何处理产品冲突？", "权限：最终权限是什么？");
  expect(screen.getByRole("button", { name: "提交澄清回答" })).toBeDisabled();
  await select("最终权限是什么？", "推荐：仅管理员导出");
  fireEvent.click(screen.getByRole("button", { name: "提交澄清回答" })); await screen.findByText(/invalid_request/);
  expect(lastBody(fetcher, "/clarifications/answers").context_conflict_resolutions).toEqual([{ question_id: "q-conflict", conflict_id: "conflict-1", expected_conflict_revision: 2, action: "answer", rationale: "由用户确定权限", final_answer_question_id: "q-permission" }]);
});

test("a committed TD review performs one recovery GET without resending and hides writes if GET fails", async () => {
  let reads = 0;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === "/api/health") return json({ status: "ok" });
    if (path === "/api/scaffold") return json({ stages: [], implemented_capabilities: [], deferred_capabilities: [] });
    if (path.endsWith("/td/reviews")) return json({ detail: { code: "workflow_sync_pending", committed: true, run_id: "run-1" } }, 503);
    if (!init && path === "/api/runs/run-1") return ++reads === 1 ? json(tdRun()) : json({ detail: { code: "unavailable" } }, 503);
    return json({}, 500);
  });
  vi.stubGlobal("fetch", fetcher); render(<App />); await openTd(); reviewIdentity(); await select("TD 人工审阅结论", "未观察到冲突");
  fireEvent.click(screen.getByRole("button", { name: "提交 TD 人工审阅" })); await screen.findByText(/命令已保存.*503.*workflow_sync_pending/);
  expect(screen.queryByRole("button", { name: "提交 TD 人工审阅" })).not.toBeInTheDocument(); expect(screen.queryByRole("button", { name: "提交 TD 单章修订" })).not.toBeInTheDocument();
  expect(fetcher.mock.calls.filter(([path]) => String(path).endsWith("/td/reviews"))).toHaveLength(1); expect(reads).toBe(2);
});

test("product change prepares a fresh parent-linked creation without copying requirement or approvals", async () => {
  const blocked = reviewedRun();
  blocked.td_review_records[0].findings[0].disposition = "product_change_required";
  setup(blocked); await openTd();
  fill("一句话需求", "旧的输入");
  fireEvent.click(screen.getByRole("button", { name: "以此 Run 为父新建需求" }));
  expect(screen.getByRole("textbox", { name: "父 Run ID（可选）" })).toHaveValue("run-1");
  expect(screen.getByRole("textbox", { name: "一句话需求" })).toHaveValue("");
  expect(screen.getByRole("button", { name: "创建 Run" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: "批准 TD" })).not.toBeInTheDocument();
});

test("renders the dedicated PRD supporting reference projection separately from authoritative facts", async () => {
  const citation = { citation_id: "citation-1", client_ref: "policy", source_id: "knowledge-source", source_sha256: hash, start: 0, end: 4, excerpt: "业务背景", purpose: "核对规则", related_candidate_ids: [], related_fact_ids: [], related_assumption_ids: [] };
  setup(run({ status: "prd_awaiting_approval", available_commands: [], clarification_batch: null, prd_draft: { revision: 1, content_hash: hash, content: "# PRD" }, knowledge_citations: [], assumptions: [], prd_supporting_context: { knowledge_citations: [citation], assumptions: [{ ...assumption, statement: "专门参考投影", affected_dimensions: [], product_impact: "none", risk: "low" }] } }));
  await screen.findByText("API 已连接"); fill("Run ID", "run-1"); fireEvent.click(screen.getByRole("button", { name: "打开 Run" }));
  await screen.findByRole("heading", { name: "PRD 草稿 · r1" });
  expect(screen.getByText("专门参考投影")).toBeInTheDocument(); expect(screen.getByText("业务背景")).toBeInTheDocument();
  expect(screen.getByText(/知识参考 · 1 项/)).toBeInTheDocument(); expect(screen.getByText("尚无已确认 FACT 或 DECISION")).toBeInTheDocument();
});

test("keeps a previous product-change judgment historical when the current TD review is stale", async () => {
  const current = reviewedRun(true);
  current.td_review_records[0].findings[0].disposition = "product_change_required";
  setup(current);
  await screen.findByText("API 已连接"); fill("Run ID", "run-1"); fireEvent.click(screen.getByRole("button", { name: "打开 Run" }));
  await screen.findByRole("heading", { name: "TD 草稿 · r2" });
  expect(screen.getByText(/当前 TD 审阅.*stale/)).toBeInTheDocument();
  expect(screen.queryByText(/当前 Run 保持服务端 blocked/)).not.toBeInTheDocument();
  expect(screen.getByText(/上一份报告登记了产品变更判断，请在当前版本逐项复查/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "以此 Run 为父新建需求" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "批准 TD" })).not.toBeInTheDocument();
});
