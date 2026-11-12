# SpecCraft AI Agent

SpecCraft 是一个个人开发项目，用于探索本地优先、契约驱动的 AI 需求分析与研发规格编制。目标是把需求整理为经过人工确认的 `PRD.md`、`TD.md` 和机器可读的交付规格。

当前仓库仍是教学脚手架，完整领域工作流正在逐步实现。Run 从可信来源和只读仓库上下文开始，经来源候选逐项确认、独立知识/假设治理、Fact Ledger、确定性五维完整度 Gate 与人工澄清后，构建并冻结 PRD。获批 PRD 单向派生八类 Design Authority 和统一 TD Blueprint；确定性 Fake TD Author 使用版本化资源生成 TD，经独立人工正文审阅、确定性质量 Issue 扫描、必要的单章节修订与复查，再由用户批准后发布带版本、Hash 和义务追溯的 DeliverySpec。SQLite 保存整个 Run 的权威状态和成功命令 ID；内存 LangGraph 在启动时从持久 Run 重建人工 Gate 路由游标。系统不具备身份认证或真实内容质量保障。

## 当前内容

- React 19、Vite、TypeScript 与 Ant Design 前端壳；
- FastAPI 健康检查、项目状态与最小 Run/审批 API；
- Pydantic Run 请求和响应 Contract；
- 严格来源准入、Fact/Decision 证据、Completeness Analyzer、原子澄清批次与回答 API；
- 有限知识引用、独立假设/上下文冲突及解决证据，参考材料不自动进入产品事实；
- PRD Blueprint（八章必填、事实与决策引用、章节内容要求、模板版本和输入摘要）、版本化草稿、局部修订、基础文档就绪检查与绑定内容 Hash 的人工审批；
- 八类 Design Authority、TD Blueprint、统一 TD、技术决定请求、TD 正文人工审阅/单章修订、确定性质量 Issue 和受限单章补丁，以及绑定版本/Hash/当前审阅的人工审批；
- `ArtifactRef`/`ArtifactEnvelope` 与不复制文档正文的机器可读 DeliverySpec；
- 来源快照与只读 Repository Harness：服务端仅绑定匿名 ExportFlow 样例，支持 GUIDE_ONLY / INDEXED_READONLY；
- `speccraft` 中的 SQLite Run Store、同步 Runner 与确定性 Fake Provider；
- LangGraph `StateGraph` 与内存 checkpointer：记录 Gate 路由游标，并在澄清后执行 PRD 编制节点；Graph State 不保存文档正文或审批证据；
- `contracts`、`agent-kernel`、`speccraft` Python 包；
- CLI 项目状态与持久 Run 摘要读取；Worker 仍为占位入口；
- 匿名需求、仓库样例与 PRD/TD 编制资源；
- 前端和后端的基础验证入口。

当前 API 支持内联需求或样例需求文件创建、来源确认、澄清回答、PRD 局部修订、技术决定、TD 人工正文审阅、TD 单章节修订、TD 质量 Issue 局部补丁及审批。创建后 Ledger 为空，原文不会自动成为 FACT。用户可拒绝原文候选并明确回答角色、流程、权限、失败与验收五维；知识引用与假设留在独立参考区，有产品影响或风险未知的假设必须解决。

PRD 批准后冻结，产品义务只取六类产品章节，背景不自动升级为技术承诺。TD 质量扫描发现结构问题、显式占位符、各章节缺少的 Authority/义务引用，以及“待核实”非阻断项；单 Issue 补丁验证目标消失与确定性规则不回归，失败保留原 TD 并记录原因，最多三次候选尝试后转人工诊断。非阻断项只能由用户绑定当前版本填写理由和披露位置接受风险，阻断项不可豁免。TD 的结构一致性检查不理解所有正文语义；必须独立记录绑定当前 PRD/TD revision、Hash 与义务的人工审阅。发现冲突会留在同一 TD Gate，修订使旧审阅失效，逐项复查后才能再次批准。产品范围需要改变时创建带可选 parent_run_id 的独立新 Run，不复制旧批准。

PRD/TD/澄清生成器仍为 Fake。输入输出实际经过 typed 任务边界：完整 UTF-8 输入 128 KiB、输出 256 KiB、最多 32 条提案/发现；角色标签和严格结构只限制写入权限，不提供语义正确性或 Prompt Injection 免疫保证。人工姓名、确认和 producer 字段均为责任声明，系统没有身份认证。

API 中的 LangGraph 使用 thread_id=run_id，Graph State 只保存 Gate 路由标识；PRD 编制节点以持久 Ledger 为输入，并在完整检查后提交草稿。领域已提交而图更新失败时，API 返回 503 workflow_sync_pending 与 committed=true，客户端先读取 Run，不能重发原命令。进程重启后 Run 与命令去重记录从 SQLite 恢复，内存检查点根据已校验的权威 Run 重建；运行中检查点异常缺失仍关闭写操作。

### 写接口版本

所有 `/api/runs` 写请求必须显式携带 `governance_contract_version: 2`，缺失返回 422 contract_version_required。澄清、TD 审阅和 TD 修订的成功 command_id 在同一 Run 内不可重用；失败不消费 ID。这是重复命令拒绝，不承诺 HTTP 幂等。现有客户端需与服务端同版升级。

```json
{"governance_contract_version": 2, "requirement": "管理员导出报表，访客无权限"}
```

主要命令入口：

| 方法与路径 | 用途 |
| --- | --- |
| POST /api/runs；GET /api/runs/{id} | 创建与读取持久 Run |
| GET /api/runs/{id}/snapshot | 一致读取 Run、单调 run_version 和模型预算；不执行 Graph |
| GET /api/runs/{id}/events?after=0 | 最多 200 条按事件 ID 排序的脱敏持久通知元数据 |
| GET /api/runs/{id}/model-budget | 只读预算策略、累计调用与候选次数 |
| GET /api/runs/{id}/commands/{command_id} | 读取新执行协议的持久命令回执；尚无后台受理写入口 |
| POST /api/runs/{id}/clarifications/answers | 来源处理、五维答案、假设/冲突一次性解决 |
| POST /api/runs/{id}/prd/revisions；POST /api/runs/{id}/approvals/prd | 单章修订与人工冻结 PRD |
| POST /api/runs/{id}/technical-decisions | 独立提交技术选择 |
| POST /api/runs/{id}/td/reviews；POST /api/runs/{id}/td/revisions | 人工正文审阅、单章修订与复查 |
| POST /api/runs/{id}/approvals/td | 当前有效审阅绑定审批，发布三产物 |

完整请求和错误结构以 FastAPI `/docs` 与共享 Pydantic Contract 为准。服务端只绑定匿名 ExportFlow 样例，知识只能显式选择 `knowledge/` 内受限文本，不提供网络检索。

## TD 质量检查与受控修复

默认仍由 Fake Author 生成示例草稿，语义正确性由用户独立审阅。当前人工报告保存后，会运行确定性最终审计，记录检查范围、当前 TD/Authority/义务/质量证据摘要；只有有效终审和当前完整人工审阅同时满足时才允许批准。结构通过不代表业务正确。

可在服务端构造 `RunRunner(..., quality_model=实现)` 注入 `QualityModel`，通过 `/td/quality/run` 显式运行有界语义发现和局部修复。模型只提供候选；服务端校验精确 Unicode 摘录、已知引用、输入绑定和资源上限，再执行目标复核、确定性回归和冻结义务守卫。每个 Issue 最多三次候选修复，一次命令最多 8 步；网络等 Provider 重试不在当前实现范围。重复候选（包含历史章节内容）、回归、预算耗尽、需要人工决定和模型边界失败均保留停止原因。全量发现遗漏不会关闭语义 Issue。

当前只有注入接口与脚本化测试替身，没有可配置远端调用器；DeepSeek 与独立 Worker 是后续接入目标。运行命令仅对创建时显式绑定了质量模型标识的 Run 投影；标识不一致时关闭执行。测试验证协议和控制流程，不证明模型内容质量。默认启动的网页不会显示自动模型执行按钮。

新 Run 的服务端预算默认累计最多 32 次模型调用、8 次 Issue 修复候选，可通过 `build_runner(..., model_budget_policy=ModelBudgetPolicy(...))` 或 Runner 的同名参数覆盖并在创建时冻结。当前接入的是质量模型调用和 Issue 补丁，PRD/TD/澄清的 Fake 不模拟外部调用消耗；后续真实接入复用同一账本。额度跨命令、跨重启保留。调用前预留额度，Provider 失败、未提交计算和后续领域提交失败也保留已消耗调用；无变化、重复及未通过检查的合法候选占用候选额度。候选已生成但复核调用失败时，也记录拒绝尝试并占用 Issue 次数。人工 Issue 补丁共用候选总额度，普通人工正文修订不计作自动候选。策略不能通过客户端扩大。达到上限形成诊断，不能视为通过。

SQLite 当前 schema 为 v3，支持从 v1/v2 原子迁移。历史 Run 不伪造事件、命令回执或模型调用次数；没有预算的历史 Run 保留读取与原有人工修订，自动质量执行返回 `model_budget_uninitialized`。预算是独立资源事实；当前 Run、Issue 和审阅/审批仍保持领域事务边界，新的质量执行结果提交后才使旧终审按账本绑定失效。

持久事件与对应 Run 版本更新同事务提交，事件只含 ID、版本、类型和时间，不含正文或模型原始响应。事件日志先保留全部记录；它为后续 SSE 提供读取依据，目前没有 SSE 订阅或外部事件派发。新的命令回执区分 accepted 与最终结果，并校验 ID 和规范化请求摘要；相同请求仍明确拒绝重复，未改为 HTTP 幂等重放。现有同步写接口的成功命令 ID 与新后台回执不同，历史记录不会被补造。

新增写命令：

| 路径（均为 POST /api/runs/{id} 下） | 用途 |
| --- | --- |
| /td/quality/run | 有界发现、自动章节候选、复核与最终审计 |
| /td/quality/decisions | 人工确认模型误报，仅对当前版本生效，不绕过结构守卫 |
| /td/issues/patch | 人工提交单章补丁；合法失败尝试也保存回执并消费命令 ID |
| /td/issues/accept-risk | 接受非阻断风险，保存实际披露文本与服务端记录定位 |

所有命令绑定 v2 治理契约和当前 TD revision/hash，执行与裁决还绑定 review_revision。校验拒绝不消耗 ID；已记录诊断或失败候选的命令属于已提交操作，不得复用 ID。模型工作在事务外暂存候选，提交前复查版本、人工审阅及质量账本；最终正文、Issue、尝试与成功命令 ID 一起提交。进程中断前尚未提交的模型计算可以重做，不保证外部调用恰好一次。

人工审阅、模型复核和终审的证据分别保留。改动正文或质量账本会使旧终审失效；自动修复会使旧人工审阅 stale。误报裁决不能代替最终审计；产品变更仍须新 Run。风险的用户位置描述只作为标签，不声称已写入指定文件；实际披露保存在 `quality_risk_acceptances`，并在页面显示。TD/DeliverySpec 的 ArtifactEnvelope 以可选 `quality_evidence_hash` 关联批准时的质量记录，正式产物仍为三份，DeliverySpec schema 不变。

历史数据新增字段有默认值；缺少本版终审证据标记的待审批 Run 关闭批准操作，重新完成人工审阅后生成真实审计记录，不伪造历史通过。已完成 Run 的历史批准保留，旧审计不能自动视为当前证据。

## 计划中的能力

- 真实 Provider 的 Reviewer/补丁生成接入和内容质量评测；
- 增加 Provider 驱动的 API 与 Workbench；
- 探索 Codex Skill 驱动的本地执行入口。

计划能力尚未在当前脚手架中实现。CodePilot、QualiFlow 和跨阶段 Supervisor 不属于当前范围。

## 项目结构

```text
apps/                 API、CLI、Web 与 Worker 入口
packages/contracts/   契约包边界
packages/agent-kernel/共享运行内核包边界
packages/speccraft/   SpecCraft 领域包边界
examples/speccraft/   匿名需求与仓库样例
learning-assets/      PRD/TD 编制资源
scripts/              本地启动脚本
```

## 启动

需要 Python 3.12 和 Node.js 20+。在仓库根目录运行：

```bash
scripts/start-scaffold.sh
```

脚本会创建 `.venv`、安装 Python 包和前端依赖，并启动 API 与 Web。端口被占用时会尝试后续可用端口。

也可以分别启动：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e 'packages/contracts[dev]' -e packages/agent-kernel -e packages/speccraft
npm --prefix apps/web install
.venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8765
npm --prefix apps/web run dev
```

API 默认把 Run 保存在仓库根目录的 `.deliveryflow-state/runs.sqlite3`；该目录已被 Git 忽略。启动前可设置 `SPECCRAFT_DB_PATH=/绝对路径/runs.sqlite3` 指定数据库。重启使用同一数据库的 API 后，已有 Run 可以继续。当前仍是单 API 进程同步编排，不支持多 Worker 并行执行；旧版本只存在于内存中的 Run 无法迁移。

API 与诊断 CLI 通过 `deliveryflow_speccraft.composition.build_runner` 共享服务端样例根目录、编制资源和模型注入方式。澄清、PRD/TD Author 和质量模型可注入；默认仍是同步 Fake 教学模式，尚未接入远端 Provider 或 Worker。

只读查询一个已知 Run 的状态与可用命令：

```bash
.venv/bin/python -m apps.cli --run-id <run_id>
.venv/bin/python -m apps.cli --run-id <run_id> --database /绝对路径/runs.sqlite3
```

CLI 同样读取 `SPECCRAFT_DB_PATH`，显式 `--database` 优先。查询不构造执行 Graph、不触发生成或审批，输出不包含需求原文；Run 不存在时退出码为 2。

## Claude Code 接入

Repo Guide 运行时技能放在 `.agents/skills/`，Claude Code 默认扫描 `.claude/skills/`。在仓库根目录建立本地软链接：

```bash
make link-skills
```

等价命令：

```bash
mkdir -p .claude
ln -sfn ../.agents/skills .claude/skills
```

`.claude/` 是本机 Host 状态，已被 `.gitignore` 忽略；`CLAUDE.md` 会导入 `AGENTS.md`，统一从 `AGENTS.md` 进入项目约定。新克隆的仓库需要执行一次上述命令。

## 验证

```bash
make verify
```

也可以单独运行前端检查：

```bash
npm --prefix apps/web run test
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

## 设计边界

- 本地运行数据和用户凭据不应提交到版本库；
- 需求仓库作为受控上下文，规格产物由明确的审批步骤确认；
- 领域流程由后端负责，前端负责交互和结果呈现；
- 只有当前阶段明确需要时才引入数据库、模型适配器或后台执行能力。
