import { Select } from "antd";
import type { ClarificationAnswer, ClarificationProposal, FactDimension, Run } from "./api";
import { AssumptionFields, emptyAssumption, TextField } from "./GovernanceCreate";
import { dimensionLabels } from "./governance";
import type { AssumptionResolution, AssumptionValues, ContextConflictResolution } from "./governance";

export type ResolutionChoice = { action?: string; rationale?: string; questionIds?: string[]; excludedId?: string; revised?: AssumptionValues; revisedAction?: "accept" | "reject" };
export type ResolutionChoices = Record<string, ResolutionChoice>;
export function governanceResolutions(run: Run, proposals: ClarificationProposal[], choices: ResolutionChoices, answers: ClarificationAnswer[]) {
  const assumptions: AssumptionResolution[] = [], conflicts: ContextConflictResolution[] = [];
  let valid = true;
  const dimensionFor = (id: string) => run.completeness.gaps.find((gap) => gap.gap_id === run.clarification_batch?.proposals.find((question) => question.question_id === id)?.gap_id)?.dimension;
  const explicitAnswer = (id: string) => answers.some((answer) => answer.question_id === id && !answer.confirmed_candidate_id);
  for (const proposal of proposals) {
    const choice = choices[proposal.question_id];
    if (!choice?.action || !choice.rationale?.trim()) { valid = false; continue; }
    if (proposal.target_kind === "assumption") {
      const item = run.assumptions.find((entry) => entry.assumption_id === proposal.target_id);
      if (!item || !["accept", "reject", "revise"].includes(choice.action)) { valid = false; continue; }
      const target = choice.action === "revise" ? choice.revised : item;
      const accept = (choice.action === "revise" ? choice.revisedAction : choice.action) === "accept";
      const needsAnswers = accept && target && (target.affected_dimensions.length > 0 || target.product_impact !== "none");
      const ids = needsAnswers ? choice.questionIds ?? [] : [];
      if (choice.action === "revise" && (!target?.statement.trim() || !choice.revisedAction)) valid = false;
      if (needsAnswers && (!target.affected_dimensions.length || ids.length !== target.affected_dimensions.length || ids.some((id) => !explicitAnswer(id))
        || target.affected_dimensions.some((dimension) => !ids.some((id) => dimensionFor(id) === dimension)))) valid = false;
      assumptions.push({ question_id: proposal.question_id, assumption_id: item.assumption_id, expected_assumption_revision: proposal.object_revision ?? item.revision,
        action: choice.action as AssumptionResolution["action"], rationale: choice.rationale.trim(), final_answer_question_ids: ids,
        ...(choice.action === "revise" ? { revised_assumption: target, revised_action: choice.revisedAction } : {}) });
    } else if (proposal.target_kind === "context_conflict") {
      const item = run.context_conflicts.find((entry) => entry.conflict_id === proposal.target_id);
      if (!item) { valid = false; continue; }
      const answerId = choice.questionIds?.[0];
      if (item.dimension && (choice.action !== "answer" || !answerId || !explicitAnswer(answerId) || dimensionFor(answerId) !== item.dimension)) valid = false;
      if (!item.dimension && (!["exclude", "irrelevant"].includes(choice.action) || (choice.action === "exclude" && ![item.left_ref.reference_id, item.right_ref.reference_id].includes(choice.excludedId ?? "")))) valid = false;
      conflicts.push({ question_id: proposal.question_id, conflict_id: item.conflict_id, expected_conflict_revision: proposal.object_revision ?? item.revision,
        action: choice.action as ContextConflictResolution["action"], rationale: choice.rationale.trim(),
        ...(choice.action === "answer" && answerId ? { final_answer_question_id: answerId } : {}),
        ...(choice.action === "exclude" && choice.excludedId ? { excluded_reference_id: choice.excludedId } : {}) });
    }
  }
  return { assumptions, conflicts, valid };
}
export default function GovernanceResolution({ run, proposals, choices, onChange, busy }: { run: Run; proposals: ClarificationProposal[]; choices: ResolutionChoices; onChange: (choices: ResolutionChoices) => void; busy: boolean }) {
  const dimensions = run.clarification_batch?.proposals.filter((item) => !item.target_kind || item.target_kind === "dimension") ?? [];
  const answerOptions = (allowed?: FactDimension[]) => dimensions.flatMap((question) => {
    const dimension = run.completeness.gaps.find((gap) => gap.gap_id === question.gap_id)?.dimension;
    return dimension && (!allowed || allowed.includes(dimension)) ? [{ value: question.question_id, label: `${dimensionLabels[dimension]}：${question.question}` }] : [];
  });
  return <>{proposals.map((question) => {
    const choice = choices[question.question_id] ?? {};
    const update = (patch: Partial<ResolutionChoice>) => onChange({ ...choices, [question.question_id]: { ...choice, ...patch } });
    const assumption = run.assumptions.find((item) => item.assumption_id === question.target_id);
    const conflict = run.context_conflicts.find((item) => item.conflict_id === question.target_id);
    const target = choice.action === "revise" ? choice.revised ?? emptyAssumption : assumption;
    const accept = (choice.action === "revise" ? choice.revisedAction : choice.action) === "accept";
    return <fieldset className="clarification-question" key={question.question_id} disabled={busy}><legend>{question.question}</legend>
      <p>{question.target_kind === "assumption" ? "假设" : "上下文冲突"} · {question.target_id} · r{question.object_revision}</p>
      {assumption && <>
        <p>{assumption.statement} · 风险 {assumption.risk} · 产品影响 {assumption.product_impact}</p>
        <label className="governance-field"><span className="field-label">假设处理</span><Select className="clarification-select" aria-label={`假设处理：${question.question}`} value={choice.action} disabled={busy} placeholder="请选择处理方式" virtual={false}
          options={[{ value: "accept", label: "接受假设" }, { value: "reject", label: "拒绝假设" }, { value: "revise", label: "修订假设" }]} onChange={(action) => update({ action, questionIds: [], ...(action === "revise" ? { revised: { statement: assumption.statement, affected_dimensions: [...assumption.affected_dimensions], risk: assumption.risk, product_impact: assumption.product_impact }, revisedAction: undefined } : {}) })} /></label>
        {choice.action === "revise" && <>
          <AssumptionFields label={`修订假设：${question.question}`} value={target!} disabled={busy} onChange={(revised) => update({ revised, questionIds: [] })} />
          <label className="governance-field"><span className="field-label">修订后明确处理</span><Select className="clarification-select" aria-label={`修订后处理：${question.question}`} value={choice.revisedAction} disabled={busy} virtual={false} placeholder="请选择接受或拒绝" options={[{ value: "accept", label: "接受修订后的假设" }, { value: "reject", label: "拒绝修订后的假设" }]} onChange={(revisedAction) => update({ revisedAction, questionIds: [] })} /></label>
        </>}
        {accept && target && (target.affected_dimensions.length > 0 || target.product_impact !== "none") && <>
          <p className="field-help">接受有产品影响的假设，需关联本次明确填写的全部受影响维度答案；引用来源候选不能代替用户决定。影响维度未明确时请先修订假设。</p>
          <label className="governance-field"><span className="field-label">关联最终维度答案</span><Select className="clarification-select" aria-label={`假设关联最终答案：${question.question}`} mode="multiple" value={choice.questionIds ?? []} disabled={busy} virtual={false} options={answerOptions(target.affected_dimensions)} onChange={(questionIds) => update({ questionIds })} /></label>
        </>}
        <TextField label={`假设处理理由：${question.question}`} value={choice.rationale ?? ""} disabled={busy} onChange={(rationale) => update({ rationale })} />
      </>}
      {conflict && <>
        <p>{conflict.reason}</p><blockquote className="source-excerpt">左侧：{conflict.left_ref.excerpt}</blockquote><blockquote className="source-excerpt">右侧：{conflict.right_ref.excerpt}</blockquote>
        <label className="governance-field"><span className="field-label">冲突处理</span><Select className="clarification-select" aria-label={`冲突处理：${question.question}`} value={choice.action} disabled={busy} virtual={false} placeholder="请选择处理方式"
          options={conflict.dimension ? [{ value: "answer", label: "关联最终维度答案" }] : [{ value: "exclude", label: "排除一侧引用" }, { value: "irrelevant", label: "与当前需求无关" }]}
          onChange={(action) => update({ action, questionIds: [], excludedId: undefined })} /></label>
        {choice.action === "answer" && <label className="governance-field"><span className="field-label">最终维度答案</span><Select className="clarification-select" aria-label={`冲突关联最终答案：${question.question}`} value={choice.questionIds?.[0]} disabled={busy} virtual={false} options={answerOptions(conflict.dimension ? [conflict.dimension] : undefined)} onChange={(id) => update({ questionIds: [id] })} /></label>}
        {choice.action === "exclude" && <label className="governance-field"><span className="field-label">排除引用</span><Select className="clarification-select" aria-label={`排除引用：${question.question}`} value={choice.excludedId} disabled={busy} virtual={false} options={[{ value: conflict.left_ref.reference_id, label: `左侧：${conflict.left_ref.excerpt}` }, { value: conflict.right_ref.reference_id, label: `右侧：${conflict.right_ref.excerpt}` }]} onChange={(excludedId) => update({ excludedId })} /></label>}
        <TextField label={`冲突处理理由：${question.question}`} value={choice.rationale ?? ""} disabled={busy} onChange={(rationale) => update({ rationale })} />
      </>}
    </fieldset>;
  })}</>;
}
export function GovernanceEvidence({ run }: { run: Run }) {
  const references = run.prd_draft ? run.prd_supporting_context : run;
  return <>
    {run.parent_run_id && <p>父 Run · <code>{run.parent_run_id}</code>（仅追溯）</p>}
    <details className="evidence-details"><summary>知识参考 · {references.knowledge_citations.length} 项</summary>
      <p className="field-help">只作参考，不自动成为产品事实；工程约束位于独立的只读工程通道。</p>
      {references.knowledge_citations.map((item) => <div key={item.citation_id}><strong>{item.client_ref}</strong> · {item.citation_id} · 参考资料
        <p>{run.source_records.find((source) => source.source_id === item.source_id)?.snapshot.normalized_path} · 用途：{item.purpose}</p><code>SHA-256 {item.source_sha256}</code>
        <blockquote className="source-excerpt">{item.excerpt}</blockquote><p>区间 [{item.start}, {item.end}) · 关联假设 {item.related_assumption_ids.join("、") || "无"}</p>
      </div>)}
    </details>
    <details className="evidence-details"><summary>未确认假设与处理历史 · {references.assumptions.length} 项</summary>
      {references.assumptions.map((item) => <div key={item.assumption_id}><strong>{item.statement}</strong><p>{item.status === "pending" ? "未确认" : item.status} · {item.assumption_id} · r{item.revision} · 风险 {item.risk} · 产品影响 {item.product_impact} · {item.affected_dimensions.map((dimension) => dimensionLabels[dimension]).join("、") || "未指定影响维度"}</p>
        {item.basis_refs.map((ref) => <p key={ref.reference_id}><code>{ref.source_sha256}</code> · {ref.excerpt}</p>)}
      </div>)}
      <ul>{run.assumption_resolution_evidence.map((item) => <li key={`${item.command_id}:${item.assumption_id}`}>{item.assumption_id} r{item.object_revision} · {item.action} → {item.resulting_status} · {item.actor_claim} · {item.rationale} · {item.resolved_at}</li>)}</ul>
    </details>
    <details className="evidence-details"><summary>上下文冲突与处理历史 · {run.context_conflicts.length} 项</summary>
      {run.context_conflicts.map((item) => <div key={item.conflict_id}><strong>{item.reason}</strong><p>{item.conflict_id} · r{item.revision} · {item.status}</p><blockquote className="source-excerpt">{item.left_ref.excerpt} ↔ {item.right_ref.excerpt}</blockquote></div>)}
      <ul>{run.context_resolution_evidence.map((item) => <li key={`${item.command_id}:${item.conflict_id}`}>{item.conflict_id} r{item.object_revision} · {item.action} · {item.actor_claim} · {item.rationale} · {item.resolved_at}</li>)}</ul>
    </details>
  </>;
}
