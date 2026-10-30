import { Button, Input, Select } from "antd";
import type { AssumptionInput, AssumptionValues, ContextConflictInput, CreateContext, InputReference, KnowledgeSelection } from "./governance";
import { dimensionOptions } from "./governance";

export const emptyAssumption: AssumptionValues = { statement: "", affected_dimensions: [], risk: "unknown", product_impact: "unknown" };
const defaultBasis: InputReference = { kind: "candidate", client_ref: "requirement_candidate" };
export function createContextError(value: CreateContext): string | null {
  const items = [...value.knowledge_selections ?? [], ...value.assumptions ?? [], ...value.context_conflicts ?? []];
  const aliases = ["requirement_source", "requirement_candidate", ...items.map((item) => item.client_ref.trim())];
  if (new Set(aliases).size !== aliases.length) return "别名必须唯一，且不能使用保留别名 requirement_source / requirement_candidate。";
  const validReference = (ref: InputReference) => Boolean(ref.client_ref.trim()) && (ref.kind !== "source" || (Number.isInteger(ref.start) && Number.isInteger(ref.end) && ref.start! >= 0 && ref.end! > ref.start!));
  if (items.some((item) => !item.client_ref.trim())
    || value.knowledge_selections?.some((item) => !item.path.trim() || !item.purpose.trim() || !Number.isInteger(item.start) || !Number.isInteger(item.end) || item.start < 0 || item.end <= item.start)
    || value.assumptions?.some((item) => !item.statement.trim() || !item.basis_refs.every(validReference))
    || value.context_conflicts?.some((item) => !item.reason.trim() || !validReference(item.left_ref) || !validReference(item.right_ref))) return "请补全新增引用、假设或冲突的必填字段，并填写有效半开区间。服务端会复核路径、引用与范围。";
  return null;
}
export function TextField({ label, value, onChange, disabled = false }: { label: string; value: string; onChange: (value: string) => void; disabled?: boolean }) {
  return <label className="governance-field"><span className="field-label">{label}</span><Input aria-label={label} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} /></label>;
}
export function ReferenceFields({ label, value, onChange, disabled }: { label: string; value: InputReference; onChange: (value: InputReference) => void; disabled: boolean }) {
  return <div className="governance-fields">
    <label className="governance-field"><span className="field-label">{label}引用类型</span><Select className="clarification-select" aria-label={`${label}引用类型`} value={value.kind} disabled={disabled} virtual={false}
      options={[{ value: "candidate", label: "需求候选" }, { value: "citation", label: "知识引用" }, { value: "source", label: "来源原文区间" }]}
      onChange={(kind) => onChange({ kind, client_ref: value.client_ref, ...(kind === "source" ? { start: 0, end: 1 } : {}) })} /></label>
    <TextField label={`${label}引用别名`} value={value.client_ref} disabled={disabled} onChange={(client_ref) => onChange({ ...value, client_ref })} />
    {value.kind === "source" && <IntervalFields label={`${label}引用`} start={value.start ?? 0} end={value.end ?? 1} disabled={disabled} onChange={(range) => onChange({ ...value, ...range })} />}
  </div>;
}
export function IntervalFields({ label, start, end, onChange, disabled }: { label: string; start: number; end: number; onChange: (range: { start: number; end: number }) => void; disabled: boolean }) {
  return <div className="interval-fields">{(["start", "end"] as const).map((key) => <label className="governance-field" key={key}><span className="field-label">{label} {key === "start" ? "起点" : "终点"}</span><Input type="number" min={key === "start" ? 0 : 1} step={1} aria-label={`${label} ${key === "start" ? "起点" : "终点"}`} value={Number.isFinite(key === "start" ? start : end) ? (key === "start" ? start : end) : ""} disabled={disabled} onChange={(event) => onChange({ start, end, [key]: event.target.value === "" ? NaN : Number(event.target.value) })} /></label>)}</div>;
}
export function AssumptionFields({ label, value, onChange, disabled }: { label: string; value: AssumptionValues; onChange: (value: AssumptionValues) => void; disabled: boolean }) {
  return <>
    <TextField label={`${label} 陈述`} value={value.statement} disabled={disabled} onChange={(statement) => onChange({ ...value, statement })} />
    <label className="governance-field"><span className="field-label">{label} 影响维度</span><Select className="clarification-select" aria-label={`${label} 影响维度`} mode="multiple" value={value.affected_dimensions} disabled={disabled} virtual={false} options={dimensionOptions} onChange={(affected_dimensions) => onChange({ ...value, affected_dimensions })} /></label>
    <label className="governance-field"><span className="field-label">{label} 风险</span><Select className="clarification-select" aria-label={`${label} 风险`} value={value.risk} disabled={disabled} virtual={false} options={[{ value: "unknown", label: "未知风险" }, { value: "low", label: "低风险" }, { value: "high", label: "高风险" }]} onChange={(risk) => onChange({ ...value, risk })} /></label>
    <label className="governance-field"><span className="field-label">{label} 产品影响</span><Select className="clarification-select" aria-label={`${label} 产品影响`} value={value.product_impact} disabled={disabled} virtual={false} options={[{ value: "unknown", label: "产品影响未知" }, { value: "none", label: "无产品影响" }, { value: "present", label: "有产品影响" }]} onChange={(product_impact) => onChange({ ...value, product_impact })} /></label>
  </>;
}
export default function GovernanceCreate({ value, onChange, busy }: { value: CreateContext; onChange: (value: CreateContext) => void; busy: boolean }) {
  const knowledge = value.knowledge_selections ?? [], assumptions = value.assumptions ?? [], conflicts = value.context_conflicts ?? [];
  const updateKnowledge = (index: number, item: KnowledgeSelection) => onChange({ ...value, knowledge_selections: knowledge.map((entry, i) => i === index ? item : entry) });
  const updateAssumption = (index: number, item: AssumptionInput) => onChange({ ...value, assumptions: assumptions.map((entry, i) => i === index ? item : entry) });
  const updateConflict = (index: number, item: ContextConflictInput) => onChange({ ...value, context_conflicts: conflicts.map((entry, i) => i === index ? item : entry) });
  const error = createContextError(value);
  return <div className="governance-create">
    <TextField label="父 Run ID（可选）" value={value.parent_run_id ?? ""} disabled={busy} onChange={(parent_run_id) => { const next = { ...value }; if (parent_run_id.trim()) next.parent_run_id = parent_run_id; else delete next.parent_run_id; onChange(next); }} />
    <p className="field-help">父 Run 只记录追溯关系；请重新提交需求，不复制事实、批准或产物。API 重启后无法找回内存 Run。</p>
    <p className="field-help">可选登记有限知识摘录、未确认假设或冲突。区间使用 Unicode 码点，起点包含、终点不包含；知识路径为服务端允许的相对路径。别名供本次引用使用，来源仍由服务端复核。</p>
    {knowledge.map((item, index) => <fieldset className="clarification-question" key={index} disabled={busy}><legend>知识引用 {index + 1}</legend>
      <TextField label={`知识引用 ${index + 1} 别名`} value={item.client_ref} disabled={busy} onChange={(client_ref) => updateKnowledge(index, { ...item, client_ref })} />
      <TextField label={`知识引用 ${index + 1} 路径`} value={item.path} disabled={busy} onChange={(path) => updateKnowledge(index, { ...item, path })} />
      <IntervalFields label={`知识引用 ${index + 1}`} start={item.start} end={item.end} disabled={busy} onChange={(range) => updateKnowledge(index, { ...item, ...range })} />
      <TextField label={`知识引用 ${index + 1} 用途`} value={item.purpose} disabled={busy} onChange={(purpose) => updateKnowledge(index, { ...item, purpose })} />
      <Button disabled={busy} onClick={() => onChange({ ...value, knowledge_selections: knowledge.filter((_, i) => i !== index) })}>移除知识引用 {index + 1}</Button>
    </fieldset>)}
    <Button disabled={busy || knowledge.length >= 8} onClick={() => onChange({ ...value, knowledge_selections: [...knowledge, { client_ref: "", path: "", start: 0, end: 1, purpose: "" }] })}>添加知识引用</Button>
    {assumptions.map((item, index) => <fieldset className="clarification-question" key={index} disabled={busy}><legend>假设 {index + 1}</legend>
      <TextField label={`假设 ${index + 1} 别名`} value={item.client_ref} disabled={busy} onChange={(client_ref) => updateAssumption(index, { ...item, client_ref })} />
      <AssumptionFields label={`假设 ${index + 1}`} value={item} disabled={busy} onChange={(fields) => updateAssumption(index, { ...item, ...fields })} />
      <ReferenceFields label={`假设 ${index + 1} 依据`} value={item.basis_refs[0]} disabled={busy} onChange={(ref) => updateAssumption(index, { ...item, basis_refs: [ref] })} />
      <Button disabled={busy} onClick={() => onChange({ ...value, assumptions: assumptions.filter((_, i) => i !== index) })}>移除假设 {index + 1}</Button>
    </fieldset>)}
    <Button disabled={busy || assumptions.length >= 32} onClick={() => onChange({ ...value, assumptions: [...assumptions, { ...emptyAssumption, client_ref: "", basis_refs: [{ ...defaultBasis }] }] })}>添加假设</Button>
    {conflicts.map((item, index) => <fieldset className="clarification-question" key={index} disabled={busy}><legend>冲突 {index + 1}</legend>
      <TextField label={`冲突 ${index + 1} 别名`} value={item.client_ref} disabled={busy} onChange={(client_ref) => updateConflict(index, { ...item, client_ref })} />
      <ReferenceFields label={`冲突 ${index + 1} 左侧`} value={item.left_ref} disabled={busy} onChange={(left_ref) => updateConflict(index, { ...item, left_ref })} />
      <ReferenceFields label={`冲突 ${index + 1} 右侧`} value={item.right_ref} disabled={busy} onChange={(right_ref) => updateConflict(index, { ...item, right_ref })} />
      <label className="governance-field"><span className="field-label">冲突 {index + 1} 维度（可选）</span><Select className="clarification-select" aria-label={`冲突 ${index + 1} 维度（可选）`} allowClear value={item.dimension ?? undefined} disabled={busy} virtual={false} options={dimensionOptions} onChange={(dimension) => updateConflict(index, { ...item, dimension: dimension ?? null })} /></label>
      <TextField label={`冲突 ${index + 1} 理由`} value={item.reason} disabled={busy} onChange={(reason) => updateConflict(index, { ...item, reason })} />
      <Button disabled={busy} onClick={() => onChange({ ...value, context_conflicts: conflicts.filter((_, i) => i !== index) })}>移除冲突 {index + 1}</Button>
    </fieldset>)}
    <Button disabled={busy || conflicts.length >= 32} onClick={() => onChange({ ...value, context_conflicts: [...conflicts, { client_ref: "", left_ref: { ...defaultBasis }, right_ref: { kind: "citation", client_ref: "" }, reason: "" }] })}>添加上下文冲突</Button>
    {error && <p className="field-help" role="status">{error}</p>}
  </div>;
}
