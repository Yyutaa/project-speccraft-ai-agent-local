import { CheckCircleOutlined, ClockCircleOutlined, FolderOpenOutlined, PlusOutlined } from "@ant-design/icons";
import { Alert, Button, Card, ConfigProvider, Input, Radio, Select, Spin, Tag } from "antd";
import { useEffect, useState } from "react";

import { api, ClarificationAnswer, Run, Scaffold, WorkflowSyncPendingError } from "./api";

const statusLabels: Record<Run["status"], string> = {
  awaiting_clarification: "等待用户澄清需求",
  prd_awaiting_approval: "等待 PRD 人工审批",
  td_awaiting_decision: "等待技术决定",
  td_awaiting_approval: "等待 TD 人工审批",
  completed: "已完成",
};

const customAnswerOption = "__custom_answer__";

const commandLabels: Record<Run["available_commands"][number], string> = {
  submit_clarification: "提交需求澄清",
  revise_prd: "局部修订 PRD",
  approve_prd: "审阅并批准 PRD",
  submit_technical_decisions: "提交技术决定",
  approve_td: "审阅并批准 TD",
};

export default function App() {
  const [scaffold, setScaffold] = useState<Scaffold | null>(null);
  const [requirement, setRequirement] = useState("");
  const [sourceMode, setSourceMode] = useState<"inline" | "file">("inline");
  const [requirementPath, setRequirementPath] = useState("");
  const [openRunId, setOpenRunId] = useState("");
  const [run, setRun] = useState<Run | null>(null);
  const [answers, setAnswers] = useState<Record<string, {
    selectedOptionId?: string;
    customAnswer?: string;
  }>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [revisionSection, setRevisionSection] = useState<string | undefined>();
  const [replacementBody, setReplacementBody] = useState("");
  const [revisionFeedback, setRevisionFeedback] = useState("");
  const [approvalActor, setApprovalActor] = useState("");
  const [approvalRationale, setApprovalRationale] = useState("");
  const [technicalAnswers, setTechnicalAnswers] = useState<Record<string, string>>({});

  useEffect(() => {
    void Promise.all([api.health(), api.scaffold()])
      .then(([, scaffoldResponse]) => setScaffold(scaffoldResponse))
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "无法连接脚手架 API");
      });
  }, []);

  async function perform(action: () => Promise<Run>) {
    setBusy(true);
    setRunError(null);
    try {
      setRun(await action());
      setAnswers({});
      setRevisionSection(undefined);
      setReplacementBody("");
      setRevisionFeedback("");
      setApprovalActor("");
      setApprovalRationale("");
      setTechnicalAnswers({});
    } catch (reason) {
      if (reason instanceof WorkflowSyncPendingError) {
        try {
          setRun(await api.readRun(reason.runId));
          setRunError("命令已保存；已刷新 Run。流程检查点同步失败时请稍后再操作。");
        } catch (readError) {
          setRun(null);
          setOpenRunId(reason.runId);
          const detail = readError instanceof Error ? readError.message : "无法读取最新 Run";
          setRunError(`命令已保存（Run ${reason.runId}），但无法读取最新状态：${detail}。请稍后按 ID 打开。`);
        }
      } else {
        setRunError(reason instanceof Error ? reason.message : "请求失败");
      }
    } finally {
      setBusy(false);
    }
  }

  const blockingProposals = run?.clarification_batch?.proposals.filter(
    (proposal) => run.clarification_batch?.blocking_gap_ids.includes(proposal.gap_id),
  ) ?? [];
  const clarificationAnswers = blockingProposals.flatMap<ClarificationAnswer>((proposal) => {
    const answer = answers[proposal.question_id];
    if (answer?.selectedOptionId === customAnswerOption) {
      return answer.customAnswer?.trim()
        ? [{ question_id: proposal.question_id, custom_answer: answer.customAnswer.trim() }]
        : [];
    }
    if (answer?.selectedOptionId) {
      return [{ question_id: proposal.question_id, selected_option_id: answer.selectedOptionId }];
    }
    return [];
  });
  const canSubmitClarification = blockingProposals.length > 0
    && clarificationAnswers.length === blockingProposals.length;
  const canCreate = sourceMode === "inline" ? Boolean(requirement.trim()) : Boolean(requirementPath.trim());

  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: "#202523",
          borderRadius: 3,
          colorText: "#202523",
        },
      }}
    >
      <header className="site-header"><span className="brand-mark">DF</span><strong>DeliveryFlow / SpecCraft</strong></header>
      <main>
        <section className="hero" aria-labelledby="page-title">
          <div><h1 id="page-title">从需求澄清到可审阅规格</h1><p className="hero-copy">输入需求，确认关键决定，再分别批准 PRD 与 TD。</p></div>
          <aside className="runtime-note">
            {error ? <Alert type="error" showIcon message="API 未连接" description={error} /> : scaffold ? (
              <p className="connection-status"><CheckCircleOutlined /> API 已连接</p>
            ) : <div className="connection-status pending"><Spin size="small" /> 正在连接 API</div>}
            <p>进程内演示 · 服务重启后 Run 消失</p>
          </aside>
        </section>

        {scaffold && (
          <>
            <section className="workspace-grid" aria-label="Run 工作台">
              <Card className="workspace-card" title={<><PlusOutlined /> 新建 Spec Run</>}>
                <label className="field-label">需求来源</label>
                <Radio.Group aria-label="需求来源" value={sourceMode} disabled={busy}
                  onChange={(event) => setSourceMode(event.target.value)}
                  options={[{ label: "直接输入", value: "inline" }, { label: "仓库内需求文件", value: "file" }]}
                />
                {sourceMode === "inline" ? (
                  <div className="source-field">
                    <label className="field-label" htmlFor="requirement">一句话需求</label>
                    <Input.TextArea id="requirement" aria-label="一句话需求" value={requirement}
                      onChange={(event) => setRequirement(event.target.value)}
                      placeholder="描述业务目标、使用者和预期结果" rows={5} disabled={busy} />
                  </div>
                ) : (
                  <div className="source-field">
                    <label className="field-label" htmlFor="requirement-path">仓库内需求文件路径</label>
                    <Input id="requirement-path" aria-label="仓库内需求文件路径" value={requirementPath}
                      onChange={(event) => setRequirementPath(event.target.value)}
                      placeholder="例如 requirements/large-excel-import.md" disabled={busy} />
                    <p className="field-help">填写服务端允许的仓库内相对路径；这里不上传文件。</p>
                  </div>
                )}
                <Button type="primary" className="run-action" disabled={!canCreate} loading={busy}
                  onClick={() => void perform(() => api.createRun(sourceMode === "inline"
                    ? { requirement: requirement.trim() }
                    : { requirement_path: requirementPath.trim() }))}>创建 Run</Button>
              </Card>
              <Card className="workspace-card current-run-card" title={<><FolderOpenOutlined /> 当前 Run</>}>
                {run ? <div className="current-run-summary">
                  <span className="meta-label">当前状态</span><Tag>{statusLabels[run.status]}</Tag>
                  <span className="meta-label">Run ID</span><code className="run-id">{run.run_id}</code>
                  <span className="meta-label">需求</span><p>{run.requirement}</p>
                  <span className="meta-label">下一项操作</span>
                  <p>{run.available_commands.map((command) => commandLabels[command]).join("、") || "没有待执行命令"}</p>
                  <a href="#run-detail">查看 Run 详情</a>
                </div> : <div className="empty-run"><strong>尚未打开 Run</strong><p>创建 Run 后，这里会显示状态和下一项需要你处理的操作。</p></div>}
                {runError && <Alert className="run-error" type="error" showIcon title={runError} />}
              </Card>
            </section>
            <section className="open-run-bar" aria-label="打开已有 Run">
              <label htmlFor="open-run-id">打开已有 Run</label>
              <Input id="open-run-id" aria-label="Run ID" value={openRunId}
                onChange={(event) => setOpenRunId(event.target.value)} placeholder="输入 Run ID" disabled={busy} />
              <Button disabled={!openRunId.trim()} loading={busy}
                onClick={() => void perform(() => api.readRun(openRunId.trim()))}>打开 Run</Button>
            </section>
            {run && <section id="run-detail" className="run-detail" aria-label="Run 工作区">
              <div className="section-heading"><h2>Run 工作区</h2><p>内容和可用操作来自服务端当前响应。</p></div>
              <div className="run-result" aria-live="polite">
                <div className="run-status">
                  <span>Run {run.run_id}</span>
                  <span>当前服务端状态 · {statusLabels[run.status]}</span>
                </div>
                <div className="detail-grid"><div className="action-panel"><h3>需要你处理</h3>
                  {run.status === "awaiting_clarification" && run.clarification_batch && (
                    <article aria-label="需求澄清">
                      <h3>需求信息待确认</h3>
                      <p>推荐项只供参考，不会自动选中。提交后，明确答案才会记为用户决定。</p>
                      {blockingProposals.map((proposal) => (
                        <fieldset className="clarification-question" key={proposal.question_id} disabled={busy}>
                          <legend>{proposal.question}</legend>
                          {proposal.recommended_option_id && (
                            <p className="clarification-recommendation">
                              <strong>Agent 推荐依据</strong>
                              <span>{proposal.recommendation_reason}</span>
                            </p>
                          )}
                          <Select
                            className="clarification-select"
                            aria-label={proposal.question}
                            placeholder="请选择答案"
                            value={answers[proposal.question_id]?.selectedOptionId}
                            onChange={(selectedOptionId) => setAnswers((current) => ({
                              ...current,
                              [proposal.question_id]: { selectedOptionId },
                            }))}
                            disabled={busy}
                            virtual={false}
                            options={[
                              ...proposal.options.map((option) => ({
                                value: option.option_id,
                                label: proposal.recommended_option_id === option.option_id
                                  ? `推荐：${option.label}`
                                  : option.label,
                              })),
                              { value: customAnswerOption, label: "其他，自定义回答" },
                            ]}
                          />
                          {answers[proposal.question_id]?.selectedOptionId === customAnswerOption && (
                            <Input
                              className="clarification-custom-answer"
                              aria-label={`自定义回答：${proposal.question}`}
                              value={answers[proposal.question_id]?.customAnswer ?? ""}
                              onChange={(event) => setAnswers((current) => ({
                                ...current,
                                [proposal.question_id]: {
                                  selectedOptionId: customAnswerOption,
                                  customAnswer: event.target.value,
                                },
                              }))}
                              placeholder="请输入自定义答案"
                              disabled={busy}
                            />
                          )}
                        </fieldset>
                      ))}
                      {run.available_commands.includes("submit_clarification") && (
                        <Button
                          className="run-action"
                          loading={busy}
                          disabled={!canSubmitClarification}
                          onClick={() => void perform(() => api.submitClarification(run, clarificationAnswers))}
                        >提交澄清回答</Button>
                      )}
                    </article>
                  )}
                  {run.available_commands.includes("revise_prd") && (
                    <div className="approval-panel">
                      <p>PRD 草稿已生成。可只修订一个章节，再审阅新版本。</p>
                      <a href="#artifacts">查看 PRD 草稿</a>
                      <label className="field-label" htmlFor="revision-section">修订章节</label>
                      <select id="revision-section" aria-label="修订章节" className="prd-section-select"
                        value={revisionSection ?? ""} disabled={busy}
                        onChange={(event) => setRevisionSection(event.target.value || undefined)}>
                        <option value="">选择章节</option>
                        {run.prd_blueprint?.sections.map((section) => (
                          <option key={section.section_id} value={section.section_id}>{section.title}</option>
                        ))}
                      </select>
                      <label className="field-label" htmlFor="replacement-body">修订后的章节正文</label>
                      <Input.TextArea id="replacement-body" aria-label="修订后的章节正文" rows={5}
                        value={replacementBody} disabled={busy} onChange={(event) => setReplacementBody(event.target.value)} />
                      <label className="field-label" htmlFor="revision-feedback">修订反馈</label>
                      <Input id="revision-feedback" aria-label="修订反馈" value={revisionFeedback} disabled={busy}
                        onChange={(event) => setRevisionFeedback(event.target.value)} />
                      <Button loading={busy} disabled={!revisionSection || !replacementBody.trim() || !revisionFeedback.trim()}
                        onClick={() => void perform(() => api.revisePrd(run, revisionSection!, replacementBody.trim(), revisionFeedback.trim()))}>
                        提交局部修订
                      </Button>
                    </div>
                  )}
                  {run.available_commands.includes("approve_prd") && (
                    <div className="approval-panel"><p>基础文档检查通过。请审阅当前 PRD 内容后人工批准。</p>
                      <label className="field-label" htmlFor="approval-actor">审批人</label>
                      <Input id="approval-actor" aria-label="审批人" value={approvalActor} disabled={busy}
                        onChange={(event) => setApprovalActor(event.target.value)} />
                      <label className="field-label" htmlFor="approval-rationale">审批理由</label>
                      <Input.TextArea id="approval-rationale" aria-label="审批理由" value={approvalRationale} disabled={busy}
                        onChange={(event) => setApprovalRationale(event.target.value)} />
                      <Button className="run-action" loading={busy} disabled={!approvalActor.trim() || !approvalRationale.trim()}
                        onClick={() => void perform(() => api.approvePrd(run, approvalActor.trim(), approvalRationale.trim()))}>批准 PRD</Button>
                    </div>
                  )}
                  {run.available_commands.includes("approve_td") && (
                    <div className="approval-panel"><p>TD 草稿已生成，请审阅下方内容后确认。</p>
                      <a href="#artifacts">查看 TD 草稿</a>
                      <label className="field-label" htmlFor="td-approval-actor">TD 审批人</label>
                      <Input id="td-approval-actor" aria-label="TD 审批人" value={approvalActor} disabled={busy}
                        onChange={(event) => setApprovalActor(event.target.value)} />
                      <label className="field-label" htmlFor="td-approval-rationale">TD 审批理由</label>
                      <Input.TextArea id="td-approval-rationale" aria-label="TD 审批理由" value={approvalRationale} disabled={busy}
                        onChange={(event) => setApprovalRationale(event.target.value)} />
                      <Button className="run-action" loading={busy} disabled={!approvalActor.trim() || !approvalRationale.trim()}
                        onClick={() => void perform(() => api.approveTd(run, approvalActor.trim(), approvalRationale.trim()))}>批准 TD</Button>
                    </div>
                  )}
                  {run.available_commands.includes("submit_technical_decisions") && (
                    <div className="approval-panel">
                      <p>生成 TD 前需要你确认以下技术取舍。这些回答不会改写已批准 PRD。</p>
                      {run.technical_decision_requests.map((request) => (
                        <div key={request.request_id}>
                          <label className="field-label" htmlFor={`technical-${request.request_id}`}>{request.question}</label>
                          <p className="field-help">{request.reason}</p>
                          <Select id={`technical-${request.request_id}`} aria-label={request.question} value={technicalAnswers[request.request_id]}
                            options={request.options.map((option) => ({ value: option, label: option }))}
                            onChange={(answer) => setTechnicalAnswers((current) => ({ ...current, [request.request_id]: answer }))} />
                        </div>
                      ))}
                      <label className="field-label" htmlFor="technical-actor">技术决策人</label>
                      <Input id="technical-actor" aria-label="技术决策人" value={approvalActor} disabled={busy}
                        onChange={(event) => setApprovalActor(event.target.value)} />
                      <Button className="run-action" loading={busy}
                        disabled={!approvalActor.trim() || run.technical_decision_requests.some((item) => !technicalAnswers[item.request_id])}
                        onClick={() => void perform(() => api.submitTechnicalDecisions(run, technicalAnswers, approvalActor.trim()))}>提交技术决定</Button>
                    </div>
                  )}
                  {run.status === "completed" && <p>PRD 与 TD 已批准，DeliverySpec 已生成。</p>}
                </div><div className="evidence-panel"><h3>来源与事实</h3>
                    <dl className="evidence-summary">
                      <dt>需求来源</dt><dd>{run.source_snapshot.normalized_path ?? "用户内联输入"}</dd>
                      <dt>需求 SHA-256</dt><dd><code>{run.source_snapshot.sha256}</code></dd>
                      <dt>仓库</dt><dd>{run.repository_binding.repository_id} · {run.repository_binding.permission}</dd>
                      <dt>上下文模式</dt><dd>只读工程上下文 · {run.repository_binding.context_mode}</dd>
                    </dl>
                    <details className="evidence-details"><summary>只读工程上下文 · {run.harness_context.entries.length} 份来源</summary>
                      <code>上下文 SHA-256 {run.harness_context.sha256}</code>
                      <ul>{run.harness_context.entries.map((entry) => (
                        <li key={entry.snapshot.normalized_path}><strong>{entry.snapshot.normalized_path}</strong>: {entry.selection_reason}<br /><code>SHA-256 {entry.snapshot.sha256}</code></li>
                      ))}</ul>
                    </details>
                    <details className="evidence-details"><summary>权威事实账本 · r{run.ledger.revision}</summary>
                      <ul>{run.ledger.facts.map((fact) => <li key={fact.fact_id}><Tag>{fact.kind === "decision" ? "用户决定" : "来源事实"}</Tag>{fact.claim}</li>)}</ul>
                    </details>
                  </div></div>
                <div id="artifacts" className="artifact-panel"><h3>规格产物</h3>
                  {!run.prd_draft && <p>需求澄清完成后才会生成 PRD 草稿。</p>}
                  {run.prd_draft && (
                    <article>
                      <h3>PRD 草稿 · r{run.prd_draft.revision}</h3>
                      <p>内容 SHA-256：<code>{run.prd_draft.content_hash}</code></p>
                      {run.prd_readiness && <p>基础文档检查：{run.prd_readiness.issues.length === 0
                        ? "通过" : run.prd_readiness.issues.map((issue) => `${issue.code}${issue.section_id ? ` (${issue.section_id})` : ""}`).join("、")}</p>}
                      <pre>{run.prd_draft.content}</pre>
                      {run.prd_approval && <p>PRD 已批准 · r{run.prd_approval.revision} · {run.prd_approval.actor} · {run.prd_approval.rationale}</p>}
                    </article>
                  )}
                  {run.td_draft && (
                    <article>
                      <h3>TD 草稿 · r{run.td_draft.revision}</h3>
                      <p>内容 SHA-256：<code>{run.td_draft.content_hash}</code></p>
                      <pre>{run.td_draft.content}</pre>
                      {run.td_approval && <p>TD 已批准 · r{run.td_approval.revision} · {run.td_approval.actor} · {run.td_approval.rationale}</p>}
                    </article>
                  )}
                  {run.delivery_spec && (
                    <article>
                      <h3>DeliverySpec</h3>
                      <pre>{JSON.stringify(run.delivery_spec, null, 2)}</pre>
                    </article>
                  )}
                </div>
              </div>
            </section>}
            <section className="stage-section" aria-labelledby="stage-title">
              <div className="section-heading">
                <h2 id="stage-title">八阶段产品路线</h2>
                <p>产品契约，不表示当前 Run 进度。</p>
              </div>
              <ol className="stage-grid">
                {scaffold.stages.map((stage, index) => (
                  <li key={stage.id}>
                    <Card className="stage-card">
                      <div className="stage-meta">
                        <span>{String(index + 1).padStart(2, "0")}</span>
                        <Tag icon={<ClockCircleOutlined />}>待实现</Tag>
                      </div>
                      <h3>{stage.title}</h3>
                      <p>{stage.description}</p>
                      <code>{stage.id}</code>
                    </Card>
                  </li>
                ))}
              </ol>
            </section>

            <details className="boundary-note"><summary>当前能力边界</summary>
              <div className="boundary-grid">
                <div><h3>已经保留</h3><ul>{scaffold.implemented_capabilities.map((item) => <li key={item}>{item}</li>)}</ul></div>
                <div><h3>计划实现</h3><ul>{scaffold.deferred_capabilities.map((item) => <li key={item}>{item}</li>)}</ul></div>
              </div>
            </details>
          </>
        )}
      </main>
      <footer>
        当前能力与启动方式见项目 README。
      </footer>
    </ConfigProvider>
  );
}
