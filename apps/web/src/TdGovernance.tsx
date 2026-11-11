import { Button, Checkbox, Input, Select, Tag } from "antd";
import { useId, useState } from "react";
import { api, type Run } from "./api";
import { IntervalFields, TextField } from "./GovernanceCreate";
import type { TdConclusion, TdDisposition, TdExcerpt, TdFinding, TdRecheck } from "./governance";

type FindingDraft = { id: string; category?: TdFinding["category"]; obligationIds: string[]; prd: TdExcerpt; td: TdExcerpt; reason: string; disposition?: TdDisposition["disposition"]; rationale: string };
type ExistingChoice = { disposition?: TdDisposition["disposition"]; rationale: string; outcome?: TdRecheck["outcome"]; excerpt: TdExcerpt };
const emptyExcerpt = (): TdExcerpt => ({ start: 0, end: 1, excerpt: "" });
const dispositionOptions = [{ value: "confirmed_conflict", label: "确认冲突" }, { value: "dismissed", label: "有理由的误报" }, { value: "product_change_required", label: "需要产品变更" }];
const conclusionOptions = [{ value: "no_conflict_observed", label: "未观察到冲突" }, { value: "changes_required", label: "需要修订技术方案" }, { value: "product_change_required", label: "需要产品变更" }];
function exactExcerpt(value: TdExcerpt, content: string) {
  return Number.isInteger(value.start) && Number.isInteger(value.end) && value.start >= 0 && value.end > value.start
    && Array.from(content).slice(value.start, value.end).join("") === value.excerpt
    && Array.from(value.excerpt).length === value.end - value.start;
}
function ExcerptFields({ label, value, content, busy, onChange }: { label: string; value: TdExcerpt; content: string; busy: boolean; onChange: (value: TdExcerpt) => void }) {
  const valid = exactExcerpt(value, content);
  const helpId = useId();
  return <div className="excerpt-fields">
    <IntervalFields label={label} start={value.start} end={value.end} disabled={busy} onChange={(range) => onChange({ ...value, ...range })} />
    <label className="governance-field"><span className="field-label">{label} 精确摘录</span><Input.TextArea aria-label={`${label} 精确摘录`} rows={3} autoSize={{ minRows: 3, maxRows: 10 }} value={value.excerpt} disabled={busy} aria-invalid={Boolean(value.excerpt) && !valid} aria-describedby={value.excerpt && !valid ? helpId : undefined} onChange={(event) => onChange({ ...value, excerpt: event.target.value })} /></label>
    {!valid && value.excerpt && <p id={helpId} className="field-help" role="status">摘录与当前正文区间不一致。请核对 Unicode 码点起点与终点；重复文字需明确所在区间。</p>}
  </div>;
}
function FindingEvidence({ finding }: { finding: TdFinding }) {
  return <div className="finding-evidence">
    <p><strong>{finding.finding_id}</strong> · {finding.category} · {finding.disposition} · 提供者 {finding.producer_kind}</p>
    <p>义务：{finding.obligation_ids.join("、")} · {finding.reason}</p>
    <p>原始 PRD 证据 [{finding.prd_excerpt.start}, {finding.prd_excerpt.end})</p><blockquote className="source-excerpt">{finding.prd_excerpt.excerpt}</blockquote>
    <p>原始 TD 证据 [{finding.td_excerpt.start}, {finding.td_excerpt.end})</p><blockquote className="source-excerpt">{finding.td_excerpt.excerpt}</blockquote>
    {finding.disposition_rationale && <p>裁决理由：{finding.disposition_rationale}</p>}
  </div>;
}
export function TdReviewEvidence({ run }: { run: Run }) {
  const review = run.td_review;
  if (!review) return null;
  return <div className="td-review-evidence">
    <h3>TD 人工审阅证据</h3><p>当前 TD 审阅 · {review.status} · 审阅版本 r{review.review_revision}</p>
    <p>当前报告：<code>{review.current_review_id ?? "尚无报告"}</code> · 未解决发现：{review.blocking_finding_ids.join("、") || "无"}</p>
    <details className="evidence-details"><summary>服务端审阅绑定</summary><dl className="evidence-summary">{Object.entries(review.binding).map(([key, value]) => <div className="binding-entry" key={key}><dt>{key}</dt><dd><code>{value}</code></dd></div>)}</dl></details>
    {run.td_readiness && <p>TD 基础结构检查 · r{run.td_readiness.revision} · {run.td_readiness.ready ? "就绪" : "未就绪"} · {run.td_readiness.issues.map((issue) => `${issue.code}${issue.section_id ? ` (${issue.section_id})` : ""}`).join("、")}</p>}
    {run.quality_gate && <section aria-label="TD 质量 Gate"><h4>TD 质量 Gate</h4><p>TD r{run.quality_gate.td_revision} · {run.quality_gate.status} · 待处理 {run.quality_gate.blocking_issue_ids.length} 项</p><ul>{run.quality_issues.map((issue) => <li key={issue.issue_id}>{issue.section_id} · {issue.severity} · {issue.status} · 尝试 {issue.attempts}/3 · {issue.evidence}{issue.last_failure ? ` · 最近失败：${issue.last_failure}` : ""}</li>)}</ul><p>补丁记录：{run.quality_patch_attempts.length} 次</p>{run.quality_risk_acceptances?.map((item) => <p key={item.issue_id + item.td_revision}>风险接受：{item.issue_id} · TD r{item.td_revision} · {item.actor_claim} · {item.rationale} · 披露于 {item.disclosure_location}</p>)}</section>}
    <section aria-label="TD 最终审计与模型执行证据"><h4>最终审计与模型执行证据</h4>
      <p>当前版本终审：{run.quality_audit_current ? "证据有效，仍需人工审批" : "缺失或已失效"} · 模型：{run.quality_provider ?? "未配置，采用人工语义审阅"}</p>
      {run.quality_executions?.map((item) => <details key={item.command_id}><summary>TD r{item.td_revision} · {item.outcome} · {item.reason} · 修复 {item.steps} 步</summary><p>{item.provider_id} · 命令 {item.command_id}</p><ul>{item.input_bindings.map((binding, index) => <li key={index}><code>{binding}</code></li>)}</ul>{item.observations.map((observation, index) => <pre className="source-excerpt" key={index}>{observation}</pre>)}</details>)}
      {run.quality_issue_decisions?.map((item, index) => <p key={index}>误报裁决 · {item.issue_id} · TD r{item.td_revision} · {item.actor_claim} · {item.rationale}</p>)}
      {run.quality_audits?.map((item) => <details key={item.audit_id}><summary>终审 TD r{item.td_revision} · {item.passed ? "通过所列检查" : "未通过"} · {item.semantic_mode}</summary><p>{item.executor} · {item.checks.join("、")}</p><code>{item.td_content_hash}</code><p>证据摘要 <code>{item.ledger_hash}</code></p></details>)}
      {run.quality_risk_acceptances?.map((item) => <blockquote className="source-excerpt" key={item.issue_id + item.td_revision}>{item.disclosure_text}</blockquote>)}
    </section>
    <details className="evidence-details"><summary>TD 修订历史 · {run.td_revisions.length} 份</summary><ul>{run.td_revisions.map((revision) => <li key={revision.revision}>r{revision.revision} · {revision.changed_section_id ?? "初稿"} · {revision.actor_claim ?? ""} · {revision.feedback ?? ""}<br /><code>SHA-256 {revision.content_hash}</code></li>)}</ul></details>
    <details className="evidence-details"><summary>人工报告历史 · {run.td_review_records.length} 份</summary>
      {run.td_review_records.map((record) => <div className="review-history-item" key={record.review_id}>
        <p><strong>{record.review_id}</strong> · r{record.review_revision} · TD r{record.binding.td_revision} · {record.human_conclusion} · {record.computed_status}</p>
        <p>{record.actor_claim} · {record.rationale} · {record.reviewed_at}</p><code>绑定 TD SHA-256 {record.binding.td_content_hash}</code>
        {record.findings.map((finding) => <FindingEvidence key={finding.finding_id} finding={finding} />)}
        {record.rechecks.map((recheck) => <div key={recheck.finding_id}><p>复查 {recheck.finding_id} · {recheck.outcome} · {recheck.rationale}</p>{recheck.td_excerpt && <blockquote className="source-excerpt">新 TD 证据 [{recheck.td_excerpt.start}, {recheck.td_excerpt.end})：{recheck.td_excerpt.excerpt}</blockquote>}</div>)}
      </div>)}
    </details>
  </div>;
}
export default function TdGovernance({ run, busy, perform, onFork }: { run: Run; busy: boolean; perform: (action: () => Promise<Run>) => Promise<void>; onFork: () => void }) {
  const [decisionIssue, setDecisionIssue] = useState<string>();
  const [decisionReason, setDecisionReason] = useState("");
  const [decisionConfirmed, setDecisionConfirmed] = useState(false);
  const [decisionCommandId] = useState(() => crypto.randomUUID());
  const [qualityActor, setQualityActor] = useState("");
  const [qualitySteps, setQualitySteps] = useState(3);
  const [qualityCommandId] = useState(() => crypto.randomUUID());
  const [actor, setActor] = useState("");
  const [rationale, setRationale] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [conclusion, setConclusion] = useState<TdConclusion>();
  const [findings, setFindings] = useState<FindingDraft[]>([]);
  const [existingChoices, setExistingChoices] = useState<Record<string, ExistingChoice>>({});
  const [section, setSection] = useState<string>();
  const [body, setBody] = useState("");
  const [feedback, setFeedback] = useState("");
  const [revisionActor, setRevisionActor] = useState("");
  const [patchIssue, setPatchIssue] = useState<string>();
  const [patchBody, setPatchBody] = useState("");
  const [patchActor, setPatchActor] = useState("");
  const [patchCommandId] = useState(() => crypto.randomUUID());
  const [riskIssue, setRiskIssue] = useState<string>();
  const [riskActor, setRiskActor] = useState("");
  const [riskRationale, setRiskRationale] = useState("");
  const [riskLocation, setRiskLocation] = useState("");
  const [riskCommandId] = useState(() => crypto.randomUUID());
  const [reviewCommandId] = useState(() => crypto.randomUUID());
  const [revisionCommandId] = useState(() => crypto.randomUUID());
  const review = run.td_review, draft = run.td_draft;
  if (!review || !draft) return null;
  const previous = run.td_review_records.at(-1);
  const oldFindings = previous?.findings.filter((item) => item.disposition !== "dismissed") ?? [];
  const newVersion = Boolean(previous && (previous.binding.td_revision !== review.binding.td_revision || previous.binding.td_content_hash !== review.binding.td_content_hash));
  const oldChoicesValid = oldFindings.every((finding) => {
    const choice = existingChoices[finding.finding_id];
    return choice && (newVersion
      ? Boolean(choice.outcome && choice.rationale.trim() && (choice.outcome !== "still_present" || exactExcerpt(choice.excerpt, draft.content)))
      : Boolean(choice.disposition && (choice.disposition !== "dismissed" || choice.rationale.trim())));
  });
  const newFindingsValid = findings.every((item) => item.category && item.obligationIds.length > 0 && item.reason.trim() && item.disposition
    && (item.disposition !== "dismissed" || item.rationale.trim()) && exactExcerpt(item.prd, run.prd_draft?.content ?? "") && exactExcerpt(item.td, draft.content));
  const canReview = Boolean(actor.trim() && rationale.trim() && confirmed && conclusion && oldChoicesValid && newFindingsValid);
  const updateFinding = (index: number, patch: Partial<FindingDraft>) => setFindings((current) => current.map((item, i) => index === i ? { ...item, ...patch } : item));
  const updateOld = (id: string, patch: Partial<ExistingChoice>) => setExistingChoices((current) => ({ ...current, [id]: { ...(current[id] ?? { rationale: "", excerpt: emptyExcerpt() }), ...patch } }));
  function submitReview() {
    const dispositions: TdDisposition[] = newVersion ? [] : oldFindings.map((finding) => ({ finding_id: finding.finding_id, disposition: existingChoices[finding.finding_id].disposition!, ...(existingChoices[finding.finding_id].rationale.trim() ? { disposition_rationale: existingChoices[finding.finding_id].rationale.trim() } : {}) }));
    const rechecks: TdRecheck[] = newVersion ? oldFindings.map((finding) => {
      const choice = existingChoices[finding.finding_id];
      return { finding_id: finding.finding_id, outcome: choice.outcome!, rationale: choice.rationale.trim(), ...(choice.outcome === "still_present" ? { td_excerpt: choice.excerpt } : {}) };
    }) : [];
    void perform(() => api.recordTdReview(run, { command_id: reviewCommandId, expected_review_revision: review!.review_revision, prior_review_id: previous?.review_id ?? null, binding: review!.binding, producer_kind: "human", actor_claim: actor.trim(), rationale: rationale.trim(), user_confirmed: true,
      human_conclusion: conclusion!, reviewed_obligation_ids: draft!.obligations.map((item) => item.obligation_id),
      findings: findings.map((item) => ({ finding_id: item.id, producer_kind: "human", category: item.category!, obligation_ids: item.obligationIds, prd_excerpt: item.prd, td_excerpt: item.td, reason: item.reason.trim(), disposition: item.disposition!, ...(item.rationale.trim() ? { disposition_rationale: item.rationale.trim() } : {}) })),
      existing_finding_dispositions: dispositions, rechecks }));
  }
  const productChange = previous?.findings.some((item) => item.disposition === "product_change_required");
  return <>
    {run.available_commands.includes("decide_td_issue") && <section className="approval-panel" aria-label="模型质量发现人工裁决">
      <h3>裁决模型误报</h3><p>仅能裁决模型发现。确定性守卫仍有效；产品要求确需变化时请新建 Run。裁决绑定当前 TD，后续修订需重新判断。</p>
      <Select aria-label="待裁决模型 Issue" value={decisionIssue} disabled={busy} placeholder="请选择模型发现" options={run.quality_issues.filter((item) => item.producer_kind === "model" && !["resolved", "accepted"].includes(item.status)).map((item) => ({ value: item.issue_id, label: item.evidence }))} onChange={setDecisionIssue} />
      <TextField label="质量裁决责任者" value={qualityActor} disabled={busy} onChange={setQualityActor} />
      <TextField label="误报裁决理由" value={decisionReason} disabled={busy} onChange={setDecisionReason} />
      <Checkbox checked={decisionConfirmed} disabled={busy} onChange={(event) => setDecisionConfirmed(event.target.checked)}>我已核对当前版本并确认该发现属于误报</Checkbox>
      <Button loading={busy} disabled={busy || !decisionIssue || !qualityActor.trim() || !decisionReason.trim() || !decisionConfirmed} onClick={() => void perform(() => api.decideTdIssue(run, decisionIssue!, qualityActor.trim(), decisionReason.trim(), decisionCommandId))}>保存误报裁决</Button>
    </section>}
    {run.available_commands.includes("run_td_quality") && <section className="approval-panel" aria-label="TD 自动质量检查表单">
      <h3>运行 TD 质量检查与受控修复</h3><p>模型发现问题并生成局部候选，由服务端验证和提交。调用会发送当前 PRD、TD 及绑定设计依据给已配置的模型；完成后仍需人工审阅和批准。</p>
      <TextField label="质量检查责任者" value={qualityActor} disabled={busy} onChange={setQualityActor} />
      <label className="governance-field"><span className="field-label">本次最多修复步数</span><Select aria-label="质量修复步数" value={qualitySteps} disabled={busy} options={[1, 3, 8].map((value) => ({ value, label: String(value) }))} onChange={setQualitySteps} /></label>
      <Button loading={busy} disabled={busy || !qualityActor.trim()} onClick={() => void perform(() => api.runTdQuality(run, qualityActor.trim(), qualitySteps, qualityCommandId))}>运行质量检查与修复</Button>
    </section>}
    {productChange && <div className="approval-panel"><Tag>产品变更需重新确认</Tag><p>上一份报告登记了产品变更判断，请在当前版本逐项复查。可以修订 TD 满足冻结 PRD，或新建 Run 重新提交需求并关联父 Run；原 Run 的事实和批准不会复制。</p><Button disabled={busy} onClick={onFork}>以此 Run 为父新建需求</Button></div>}
    {run.available_commands.includes("record_td_review") && <section className="approval-panel" aria-label="TD 人工审阅表单">
      <h3>记录 TD 人工审阅</h3><p>请核对冻结 PRD 义务与当前 TD。结构检查不证明语义正确；结论、发现和逐项裁决由你明确填写。</p>
      <ul>{draft.obligations.map((obligation) => <li key={obligation.obligation_id}><strong>{obligation.obligation_id}</strong>：{obligation.statement}</li>)}</ul>
      {oldFindings.map((finding) => {
        const choice = existingChoices[finding.finding_id];
        return <fieldset className="clarification-question" key={finding.finding_id} disabled={busy}><legend>已有发现 {finding.finding_id}</legend><FindingEvidence finding={finding} />
          {newVersion ? <>
            <label className="governance-field"><span className="field-label">本次逐项复查</span><Select className="clarification-select" aria-label={`发现 ${finding.finding_id} 复查结果`} value={choice?.outcome} disabled={busy} virtual={false} placeholder="请选择复查结果" options={[{ value: "fixed", label: "已修复" }, { value: "still_present", label: "仍然存在" }, { value: "not_applicable", label: "不再适用" }]} onChange={(outcome) => updateOld(finding.finding_id, { outcome })} /></label>
            <TextField label={`发现 ${finding.finding_id} 复查理由`} value={choice?.rationale ?? ""} disabled={busy} onChange={(value) => updateOld(finding.finding_id, { rationale: value })} />
            {choice?.outcome === "still_present" && <ExcerptFields label={`发现 ${finding.finding_id} 新 TD`} value={choice.excerpt} content={draft.content} busy={busy} onChange={(excerpt) => updateOld(finding.finding_id, { excerpt })} />}
          </> : <>
            <label className="governance-field"><span className="field-label">本次裁决</span><Select className="clarification-select" aria-label={`发现 ${finding.finding_id} 本次裁决`} value={choice?.disposition} disabled={busy} virtual={false} placeholder="请选择本次裁决" options={dispositionOptions} onChange={(disposition) => updateOld(finding.finding_id, { disposition })} /></label>
            <TextField label={`发现 ${finding.finding_id} 裁决理由`} value={choice?.rationale ?? ""} disabled={busy} onChange={(value) => updateOld(finding.finding_id, { rationale: value })} />
          </>}
        </fieldset>;
      })}
      {findings.map((finding, index) => {
        const label = `新发现 ${index + 1}`;
        return <fieldset className="clarification-question" key={finding.id} disabled={busy}><legend>{label}</legend>
          <label className="governance-field"><span className="field-label">{label} 类型</span><Select className="clarification-select" aria-label={`${label} 类型`} value={finding.category} disabled={busy} virtual={false} placeholder="请选择类型" options={[{ value: "product_conflict", label: "产品冲突" }, { value: "uncertainty", label: "不确定项" }]} onChange={(category) => updateFinding(index, { category })} /></label>
          <label className="governance-field"><span className="field-label">{label} 关联义务</span><Select className="clarification-select" aria-label={`${label} 关联义务`} mode="multiple" value={finding.obligationIds} disabled={busy} virtual={false} options={draft.obligations.map((item) => ({ value: item.obligation_id, label: `${item.obligation_id}：${item.statement}` }))} onChange={(obligationIds) => updateFinding(index, { obligationIds })} /></label>
          <p className="field-help">复制完整文档中的原文摘录并给出精确 Unicode 码点半开区间。可在下方规格产物查看正文；页面不选择语义冲突或自动裁决。</p>
          <ExcerptFields label={`${label} PRD`} value={finding.prd} content={run.prd_draft?.content ?? ""} busy={busy} onChange={(prd) => updateFinding(index, { prd })} />
          <ExcerptFields label={`${label} TD`} value={finding.td} content={draft.content} busy={busy} onChange={(td) => updateFinding(index, { td })} />
          <TextField label={`${label} 理由`} value={finding.reason} disabled={busy} onChange={(reason) => updateFinding(index, { reason })} />
          <label className="governance-field"><span className="field-label">{label} 裁决</span><Select className="clarification-select" aria-label={`${label} 裁决`} value={finding.disposition} disabled={busy} virtual={false} placeholder="请选择人工裁决" options={dispositionOptions} onChange={(disposition) => updateFinding(index, { disposition })} /></label>
          <TextField label={`${label} 裁决理由`} value={finding.rationale} disabled={busy} onChange={(value) => updateFinding(index, { rationale: value })} />
          <Button disabled={busy} onClick={() => setFindings((current) => current.filter((item) => item.id !== finding.id))}>移除新发现 {index + 1}</Button>
        </fieldset>;
      })}
      <Button disabled={busy} onClick={() => setFindings((current) => [...current, { id: crypto.randomUUID(), obligationIds: [], prd: emptyExcerpt(), td: emptyExcerpt(), reason: "", rationale: "" }])}>添加 TD 发现</Button>
      <TextField label="TD 审阅人" value={actor} disabled={busy} onChange={setActor} />
      <TextField label="TD 审阅理由" value={rationale} disabled={busy} onChange={setRationale} />
      <label className="governance-field"><span className="field-label">TD 人工审阅结论</span><Select className="clarification-select" aria-label="TD 人工审阅结论" value={conclusion} disabled={busy} virtual={false} placeholder="请选择你的审阅结论" options={conclusionOptions} onChange={setConclusion} /></label>
      <Checkbox checked={confirmed} disabled={busy} onChange={(event) => setConfirmed(event.target.checked)}>我已逐项核对全部冻结义务，并明确提交本次人工审阅</Checkbox>
      <p className="field-help">勾选是责任声明，不证明业务正确性；报告不会自动批准 TD。</p>
      <Button className="run-action" loading={busy} disabled={!canReview} onClick={submitReview}>提交 TD 人工审阅</Button>
    </section>}
    {run.available_commands.includes("revise_td") && <section className="approval-panel" aria-label="TD 单章修订表单">
      <h3>TD 单章修订</h3><p>只替换一个 canonical 章节。新版本需重新审阅，已批准 PRD 与冻结义务不变。</p>
      <label className="governance-field"><span className="field-label">TD 修订章节</span><Select className="clarification-select" aria-label="TD 修订章节" value={section} disabled={busy} virtual={false} placeholder="请选择一个章节" options={run.td_blueprint?.sections.map((item) => ({ value: item.section_id, label: item.title }))} onChange={setSection} /></label>
      <label className="governance-field"><span className="field-label">TD 修订后的章节正文</span><Input.TextArea aria-label="TD 修订后的章节正文" rows={6} autoSize={{ minRows: 6, maxRows: 20 }} value={body} disabled={busy} onChange={(event) => setBody(event.target.value)} /></label>
      <TextField label="TD 修订反馈" value={feedback} disabled={busy} onChange={setFeedback} />
      <TextField label="TD 修订人" value={revisionActor} disabled={busy} onChange={setRevisionActor} />
      <p className="field-help">TD r{draft.revision} · 审阅 r{review.review_revision} · 命令 <code>{revisionCommandId}</code></p>
      <Button className="run-action" loading={busy} disabled={!section || !body.trim() || !feedback.trim() || !revisionActor.trim()} onClick={() => void perform(() => api.reviseTd(run, section!, body, feedback.trim(), revisionActor.trim(), revisionCommandId))}>提交 TD 单章修订</Button>
    </section>}
    {run.available_commands.includes("patch_td_issue") && <section className="approval-panel" aria-label="TD 质量补丁表单">
      <h3>修复一项 TD 质量问题</h3><p>提交后由服务端验证目标问题和全文回归。失败会保留原 TD 并记录诊断；成功会产生新版本，需要重新人工审阅。</p>
      <label className="governance-field"><span className="field-label">目标 Issue</span><Select className="clarification-select" aria-label="目标 TD 质量 Issue" value={patchIssue} disabled={busy} virtual={false} placeholder="请选择一项" options={run.quality_issues.filter((item) => ["open", "reopened"].includes(item.status) && item.attempts < 3).map((item) => ({ value: item.issue_id, label: `${item.section_id} · ${item.evidence}` }))} onChange={setPatchIssue} /></label>
      <label className="governance-field"><span className="field-label">修复后的完整章节正文</span><Input.TextArea aria-label="修复后的完整章节正文" rows={6} autoSize={{ minRows: 6, maxRows: 20 }} value={patchBody} disabled={busy} onChange={(event) => setPatchBody(event.target.value)} /></label>
      <TextField label="质量补丁责任者" value={patchActor} disabled={busy} onChange={setPatchActor} />
      <Button className="run-action" loading={busy} disabled={!patchIssue || !patchBody.trim() || !patchActor.trim()} onClick={() => {
        const issue = run.quality_issues.find((item) => item.issue_id === patchIssue);
        const sectionId = run.td_blueprint?.sections.find((item) => item.title === issue?.section_id)?.section_id;
        if (sectionId) void perform(() => api.patchTdIssue(run, patchIssue!, sectionId, patchBody, patchActor.trim(), patchCommandId));
      }}>提交局部质量补丁</Button>
    </section>}
    {run.available_commands.includes("accept_td_quality_risk") && <section className="approval-panel" aria-label="TD 风险接受表单">
      <h3>接受非阻断质量风险</h3><p>只适用于当前 TD 版本的非阻断 Issue；再次修订后需要重新判断。阻断问题不能接受风险。</p>
      <label className="governance-field"><span className="field-label">非阻断 Issue</span><Select className="clarification-select" aria-label="非阻断 TD Issue" value={riskIssue} disabled={busy} virtual={false} placeholder="请选择一项" options={run.quality_issues.filter((item) => item.severity === "major" && ["open", "reopened", "failed"].includes(item.status)).map((item) => ({ value: item.issue_id, label: `${item.section_id} · ${item.evidence}` }))} onChange={setRiskIssue} /></label>
      <TextField label="风险接受责任者" value={riskActor} disabled={busy} onChange={setRiskActor} />
      <TextField label="风险接受理由" value={riskRationale} disabled={busy} onChange={setRiskRationale} />
      <TextField label="风险披露位置" value={riskLocation} disabled={busy} onChange={setRiskLocation} />
      <Button className="run-action" loading={busy} disabled={!riskIssue || !riskActor.trim() || !riskRationale.trim() || !riskLocation.trim()} onClick={() => void perform(() => api.acceptTdQualityRisk(run, riskIssue!, riskActor.trim(), riskRationale.trim(), riskLocation.trim(), riskCommandId))}>提交风险接受</Button>
    </section>}
  </>;
}
