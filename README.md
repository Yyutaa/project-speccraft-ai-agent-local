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
- CLI 项目状态与持久 Run 摘要读取；独立本地 Worker 支持后台澄清候选、PRD/TD 编制与有界质量任务；
- 匿名需求、仓库样例与 PRD/TD 编制资源；
- 前端和后端的基础验证入口。

当前 API 支持内联需求或样例需求文件创建、来源确认、澄清回答、PRD 局部修订、技术决定、TD 人工正文审阅、TD 单章节修订、TD 质量 Issue 局部补丁及审批。创建后 Ledger 为空，原文不会自动成为 FACT。用户可拒绝原文候选并明确回答角色、流程、权限、失败与验收五维；知识引用与假设留在独立参考区，有产品影响或风险未知的假设必须解决。

PRD 批准后冻结，产品义务只取六类产品章节，背景不自动升级为技术承诺。TD 质量扫描发现结构问题、显式占位符、各章节缺少的 Authority/义务引用，以及“待核实”非阻断项；单 Issue 补丁验证目标消失与确定性规则不回归，失败保留原 TD 并记录原因，最多三次候选尝试后转人工诊断。非阻断项只能由用户绑定当前版本填写理由和披露位置接受风险，阻断项不可豁免。TD 的结构一致性检查不理解所有正文语义；必须独立记录绑定当前 PRD/TD revision、Hash 与义务的人工审阅。发现冲突会留在同一 TD Gate，修订使旧审阅失效，逐项复查后才能再次批准。产品范围需要改变时创建带可选 parent_run_id 的独立新 Run，不复制旧批准。

默认同步教学流程的 PRD/TD/澄清生成器仍为 Fake；独立后台入口支持 DeepSeek 澄清候选、PRD/TD 编制与有界质量任务，接入范围与限制见下文。输入输出实际经过 typed 任务边界：完整 UTF-8 输入 128 KiB、输出 256 KiB、最多 32 条提案/发现；角色标签和严格结构只限制写入权限，不提供语义正确性或 Prompt Injection 免疫保证。人工姓名、确认和 producer 字段均为责任声明，系统没有身份认证。

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
| GET /api/runs/{id}/commands/{command_id} | 读取持久命令回执，区分受理、已提交业务决定及后继任务结果 |
| POST /api/runs/{id}/clarifications/answers | 来源处理、五维答案、假设/冲突一次性解决 |
| POST /api/runs/{id}/prd/revisions；POST /api/runs/{id}/approvals/prd | 单章修订与人工冻结 PRD |
| POST /api/runs/{id}/technical-decisions | 独立提交技术选择 |
| POST /api/runs/{id}/td/reviews；POST /api/runs/{id}/td/revisions | 人工正文审阅、单章修订与复查 |
| POST /api/runs/{id}/approvals/td | 当前有效审阅绑定审批，发布三产物 |

完整请求和错误结构以 FastAPI `/docs` 与共享 Pydantic Contract 为准。服务端只绑定匿名 ExportFlow 样例，知识只能显式选择 `knowledge/` 内受限文本，不提供网络检索。

## TD 质量检查与受控修复

默认仍由 Fake Author 生成示例草稿，语义正确性由用户独立审阅。当前人工报告保存后，会运行确定性最终审计，记录检查范围、当前 TD/Authority/义务/质量证据摘要；只有有效终审和当前完整人工审阅同时满足时才允许批准。结构通过不代表业务正确。

可在服务端构造 `RunRunner(..., quality_model=实现)` 注入 `QualityModel`，通过 `/td/quality/run` 显式运行有界语义发现和局部修复。模型只提供候选；服务端校验精确 Unicode 摘录、已知引用、输入绑定和资源上限，再执行目标复核、确定性回归和冻结义务守卫。每个 Issue 最多三次候选修复，一次命令最多 8 步；网络等 Provider 重试不在当前实现范围。重复候选（包含历史章节内容）、回归、预算耗尽、需要人工决定和模型边界失败均保留停止原因。全量发现遗漏不会关闭语义 Issue。

DeepSeek HTTP 适配器与独立 Worker 已覆盖澄清、PRD/TD Author 和质量循环；脚本化 HTTP 替身验证了机制，真实 Provider 连通性、远端协议与语义效果仍须单独验收。运行命令仅对创建时显式绑定了质量模型标识的 Run 投影；标识不一致时关闭执行。测试验证协议和控制流程，不证明模型内容质量。默认启动的网页不会显示自动模型执行按钮。

新 Run 的服务端预算默认累计最多 32 次模型调用、8 次 Issue 修复候选，可通过 `build_runner(..., model_budget_policy=ModelBudgetPolicy(...))` 或 Runner 的同名参数覆盖并在创建时冻结。当前接入的是质量模型调用、Issue 补丁和 managed 各模型角色的每次 HTTP 尝试；旧同步 PRD/TD/澄清的 Fake 不模拟外部调用消耗。额度跨命令、跨重启保留。调用前预留额度，Provider 失败、未提交计算和后续领域提交失败也保留已消耗调用；无变化、重复及未通过检查的合法候选占用候选额度。候选已生成但复核调用失败时，也记录拒绝尝试并占用 Issue 次数。人工 Issue 补丁共用候选总额度，普通人工正文修订不计作自动候选。策略不能通过客户端扩大。达到上限形成诊断，不能视为通过。

SQLite 当前 schema 为 v5，支持从 v1/v2/v3/v4 原子迁移；任务表增加 nullable quality_request，旧任务读为 null，不补造质量请求或消耗；嵌套人工命令使用 SAVEPOINT 并由外层事务控制提交。旧 Run 不自动变为后台模式。历史 Run 不伪造事件、命令回执或模型调用次数；没有预算的历史 Run 保留读取与原有人工修订，自动质量执行返回 `model_budget_uninitialized`。预算是独立资源事实；当前 Run、Issue 和审阅/审批仍保持领域事务边界，新的质量执行结果提交后才使旧终审按账本绑定失效。

持久事件与对应 Run 版本更新同事务提交，事件只含 ID、版本、类型和时间，不含正文或模型原始响应。事件日志先保留全部记录；原生 SSE 从该日志读取失效提示，无独立外部消息派发。新的命令回执区分 accepted 与最终结果，并校验 ID 和规范化请求摘要；相同请求仍明确拒绝重复，未改为 HTTP 幂等重放。现有同步写接口的成功命令 ID 与新后台回执不同，历史记录不会被补造。

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

- 真实 Provider 的远端连通性、协议正确性和内容质量评测；
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

脚本会在需要时创建 `.venv`、安装依赖，再统一启动 API、Web 及可选独立 Worker。默认从 API 8790、Web 5190 开始有界寻找空闲端口，两个端口保持不同；不会停止或占用其他项目已有监听端口。

也可以分别启动：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e 'packages/contracts[dev]' -e packages/agent-kernel -e packages/speccraft
npm --prefix apps/web install
.venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8765
npm --prefix apps/web run dev
```

API 默认把 Run 保存在仓库根目录的 `.deliveryflow-state/runs.sqlite3`；该目录已被 Git 忽略。启动前可设置 `SPECCRAFT_DB_PATH=/绝对路径/runs.sqlite3` 指定数据库。重启使用同一数据库的 API 后，已有 Run 可以继续。默认网页仍使用单 API 进程同步教学编排；后台入口使用一个独立本地 Worker，统一启动脚本按配置启动，不提供多机编排；旧版本只存在于内存中的 Run 无法迁移。

API 与诊断 CLI 通过 `deliveryflow_speccraft.composition.build_runner` 共享服务端样例根目录、编制资源和模型注入方式。澄清、PRD/TD Author 和质量模型可注入；默认网页仍是同步 Fake 教学模式；后台模型任务入口另需 DeepSeek 配置与独立 Worker。

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


## Provider-driven 后台入口（模块五第 18 节）

已接通 `创建 Run → 澄清候选 → 用户明确提交 → 后台 PRD → 人工修订/批准 → 后台 TD / 人工技术决定 → 有界质量修复与终审 → 独立人工正文审阅/批准 → 三份正式产物`。managed Run 继续使用专用命令接口；旧同步写接口返回 `execution_mode_conflict`。网页默认保留显式 Fake 教学模式，切换“后台模型（managed）”即可创建或打开后台 Run，使用 REST 工作台和 SSE 更新提示。

API 与 Worker 必须使用同一个 `SPECCRAFT_DB_PATH`。两个进程的服务端环境均须设置：

- `SPECCRAFT_PROVIDER=deepseek`；
- `SPECCRAFT_MODEL`：填写账号实际可用的模型 ID，不猜测或静默替换；
- `DEEPSEEK_API_KEY`：通过本机进程环境安全提供，不写入版本库；
- 可选 `SPECCRAFT_BASE_URL`：仅接受官方 `https://api.deepseek.com` 或 `/v1`，默认前者；不跟随重定向。

不自动读取 `.env` 或其他项目的配置。缺少必需配置时，新建后台 Run 返回 503，Worker 启动退出 2，只显示配置名称，不回退 Fake。

分别启动 API 和 Worker：

```bash
make run-api
make run-worker
```

Worker 也支持单次处理和显式数据库路径：

```bash
.venv/bin/python -m apps.worker --once --database /绝对路径/runs.sqlite3
```

创建后台 Run 的请求示例：

```bash
curl -sS http://127.0.0.1:8765/api/managed/runs \
  -H 'Content-Type: application/json' \
  -d '{"execution_contract_version":1,"request":{"governance_contract_version":2,"requirement":"创建导出工具。"}}'
```

返回 202 和 `run_id`、`command_id`、`job_id`、accepted 回执。此时状态为 `context_preparing`，没有澄清批次或可写命令。通过 REST 读取：

- `GET /api/runs/{run_id}/snapshot`：权威 Run 的版本化投影与预算；
- `GET /api/runs/{run_id}/jobs/{job_id}`：安全任务摘要，不返回模型输入、思考过程或凭据；
- `GET /api/runs/{run_id}/commands/{command_id}`：受理与最终结果；
- `GET /api/runs/{run_id}/events`：持久更新提示，尚非 SSE。

Worker 成功后停在 `awaiting_clarification`，Ledger 仍为空，用户尚未确认任何事实。失败回执保留稳定错误码；鉴权、余额、协议与结构错误不自动重试。临时网络/超时/429/5xx 最多尝试两次，这是冻结在 Provider profile 中的本地试点策略；每次请求前均扣持久调用额度，进程退出或结果保存失败不退还。新 Worker 接管也只能使用剩余额度，不承诺模型调用恰好一次。失败重试和取消通过下述显式接口完成；可用操作来自任务摘要的 available_commands。

Provider/model、端点、输出 token 上限、思考模式和超时策略冻结绑定；凭据不入库，轮换 key 不改变配置绑定。模型响应只作为候选，通过既有用途、绑定、引用和资源校验；HTTP 成功或结构通过均不代表业务语义正确。每个 Run 只允许一个活动任务；默认租约 30 秒、独立连接每 10 秒续租。硬退出后租约过期可接管，旧 epoch 的提交和调用预留拒绝。GET 与 Graph 启动不执行 managed 模型任务。

创建请求沿用“每次创建新 Run”的语义，不提供创建幂等重放。已受理 Run 的任务回执和消耗可在重启后读取；不要把 Worker 进程退出 0 或模型调用成功当作整条业务流程完成。真实 DeepSeek 连通性和语义质量需单独验收，HTTP 替身测试不能代替它们。


### 提交澄清并后台生成 PRD

```text
POST /api/managed/runs/{run_id}/clarifications
{
  "execution_contract_version": 1,
  "expected_run_version": 最新 snapshot.run_version,
  "request": 原 SubmitClarificationRequest 完整治理 v2 请求
}
```

嵌套 request 仍需显式 command_id、批次/账本版本、操作者声明、理由、user_confirmed=true，以及全部来源处理和阻塞问题答案。没有默认事实或自动选择推荐答案。返回 202 时，Run 已为 prd_preparing，用户账本、准入证据、成功命令 ID、PRD 任务与事件同事务保存；API 不调用 Author。Worker 从持久任务编制，成功后保存当前 PRD Revision 和基础检查结果，停在 prd_awaiting_approval，不生成批准或 TD。

回执的 domain_committed=true 表示该命令已有确定性业务结果提交。它可以与 accepted、failed 或 cancelled 同时出现：例如澄清已入账，而后继模型失败。此时先读取 Run/任务/回执，通过显式重试处理，不重发或撤销用户答案。模型结果提交失败保留已确认账本及调用消耗，尚未提交的 PRD 正文、Revision 和最终回执一起回滚。

回执新增字段通过 JSON 兼容默认值读取：旧记录缺少 domain_committed 时为 false，缺少 actor_claim/rationale 时为 null；这是兼容读取，不据此补造旧记录的提交或责任证据，也不能仅凭 false 推断历史上没有业务变化。

### 显式取消和重试

```text
POST /api/managed/runs/{run_id}/jobs/{job_id}/cancel   → 200
POST /api/managed/runs/{run_id}/jobs/{job_id}/retry    → 202
```

两个请求均需 execution_contract_version=1、governance_contract_version=2、expected_run_version、全 Run 共享且未使用的 command_id、actor_claim、rationale 和 user_confirmed=true。操作者声明与理由进入持久回执，不表示系统已经认证身份。GET /api/runs/{run_id}/jobs/{job_id} 返回安全摘要、当前 run_version 和 available_commands：活动任务可取消，失败/取消且 Run 输入基线仍匹配、没有其他活动任务、总额度尚有余量时可重试。

取消不删除账本、审批或已消耗调用；旧 epoch 不能提交迟到结果。显式重试创建新 job 和回执，复用原任务输入，不重新执行来源准入或用户决策；原失败/取消回执保留。每个新 job 使用冻结的尝试上限，Run 总调用预算持续累计、不退款。已成功任务、其他 Run 的 job、旧 Run version、变更后的业务输入和总预算耗尽不能被当作正常重试；服务端编制资源或规则变化还会在执行前拒绝旧绑定，不发出模型请求。

相同 command_id / 相同规范化请求返回 duplicate_command，不隐式重放成功结果；同 ID 不同请求返回 command_payload_conflict。先读回执确认已有结果，不以网络超时为由盲目创建重试。网页默认使用显式 legacy Fake 教学模式，可切换 managed 工作台；后台任务和正文通过 REST 读取，SSE 只负责更新提示。


### PRD 批准、TD 编制和人工命令

`POST /api/managed/runs/{run_id}/prd/approve` 使用 execution v1、当前 expected_run_version、全局唯一于本 Run 的 command_id，request 嵌套既有 PRD 审批请求（governance v2、revision、content_hash、actor、rationale）。返回 202 前冻结批准 PRD、Authority、TD Blueprint 和 TD 任务，状态为 td_preparing。模型失败保留批准，不重新开放 PRD。Worker 成功后停在 td_awaiting_decision 或 td_awaiting_approval。

`POST /api/managed/runs/{run_id}/technical-decisions` 使用下述人工命令外层和嵌套既有技术决定请求。决定先持久入账，随后排队 TD 模型任务；失败不撤销决定。

人工同步命令统一外层：

```json
{
  "execution_contract_version": 1,
  "governance_contract_version": 2,
  "expected_run_version": 12,
  "command_id": "unique-user-command",
  "actor_claim": "用户责任声明",
  "rationale": "本次操作理由",
  "user_confirmed": true,
  "request": {"governance_contract_version": 2}
}
```

request 按具体路由使用原契约的完整字段；如其中存在 command_id、actor_claim / actor、rationale，必须与外层一致。响应为 RunSnapshot，含最新 run_version。人工命令路径：

- `/api/managed/runs/{run_id}/prd/revisions`：单节正文替换，绑定当前 PRD revision/hash；批准后拒绝。
- `/api/managed/runs/{run_id}/td/revisions`：单节替换，绑定 TD revision/hash/review_revision，旧审阅失效。
- `/api/managed/runs/{run_id}/td/reviews`：独立人工正文审阅和逐项发现复查。
- `/api/managed/runs/{run_id}/td/quality/decisions`：人工误报裁决，无需模型在线。
- `/api/managed/runs/{run_id}/td/quality/risk-acceptances`：仅允许既有守卫许可的非阻断风险。
- `/api/managed/runs/{run_id}/td/approve`：当前终审、正文审阅和结构守卫通过后，批准并发布 PRD.md、TD.md、DeliverySpec.json。

所有路径使用 POST。活动任务存在时拒绝人工改写；人工写入、成功 ID、回执和更新事件同事务提交。相同命令不做成功重放。

### 后台质量批次

`POST /api/managed/runs/{run_id}/td/quality/run` 使用 execution v1、expected_run_version、rationale、严格 user_confirmed=true，以及 request 嵌套既有 QualityCycleRequest（治理 v2、command_id、actor_claim、当前 TD revision/hash/review_revision、max_steps）。返回 202，不调用模型。只有创建时绑定了对应 Provider 标识的 Run 才能执行；历史无绑定 Run 不自动升级。

Worker 复用 discover → repair → verify → final_audit，真实 HTTP 适配器接收每个 typed 子任务；每次请求记录实际 input_binding。一次批次调用预留上限为 `(2 + 2 * max_steps) * profile.max_attempts`，受 Run 总调用额度进一步限制；每次 HTTP 操作瞬时重试不超过 profile.max_attempts。max_steps 范围 1～8，表示候选修复步数，不代表质量已收敛。每 Issue 最多 3 个候选；managed 额外检查持久候选记录，未提交/取消后也不能借重启重置次数。Run 默认累计最多 32 次 HTTP、8 个候选。

正文、Issue、尝试和终审在批次最后校验租约/权威基线后原子保存；计算中断可在剩余额度内重做，调用与已登记候选不退还。合法诊断批次的任务可以 succeeded，表示诊断已保存；是否通过须读取 quality_executions 的 outcome/reason 和当前 Gate，不能把 job succeeded 当作质量通过。鉴权失败、预算耗尽、重复候选和回归均不能产生通过审计。修复正文使旧人工审阅 stale，模型终审不能代替用户批准。质量失败/取消可通过既有显式控制重试，Run 消耗继续累计。


## Run 工作台与 SSE（第19节）

网页“执行模式”明确区分 Fake 同步教学和后台模型。后台模式需要先配置第18节要求的 Provider 环境并启动 API + Worker。按 ID 打开后台 Run 时选择“后台模型（managed）”；打开后使用服务端 execution_mode 确定命令入口，不按用户猜测推进流程。

- `GET /api/runs/{run_id}/workbench` 返回一致的 Run、run_version、累计预算、execution_mode、当前有效 available_commands、最新 50 个任务及安全命令回执、event_cursor。jobs_truncated 表示存在更早任务，完整单命令回执仍可按 ID 读取。
- 顶层 available_commands 合并领域能力与活动任务/预算/Provider绑定限制。内部 run.available_commands 是权威领域基础能力，不因 UI 读取而改写持久 Run；工作台展示顶层命令。JobSummary 单独给出取消/重试。
- `GET /api/runs/{run_id}/events/stream?after={event_cursor}` 返回 text/event-stream。原生 EventSource 重连也可用 Last-Event-ID，Header 优先于 query；非法游标 422，未知 Run 404，在发送流头前校验。
- 新连接 ready 促使 REST 校准；初次 after=0 从当前游标开始。有效游标补发 Run 内后续 update；不再保留、越界或其他 Run 的游标发 reset，客户端重新读工作台。当前日志全量保留，没有定时清理；如以后清理，reset 是恢复边界。
- SSE data 仅含 event_id、run_id、run_version、event_type、invalidates，不含正文、来源原文或模型响应。每 15 秒发送无 id 的命名 heartbeat 和 keep-alive 注释，心跳不推进游标、不触发 REST；完成 Run 发 terminal 后结束。服务端每 0.5 秒短读持久事件，不在连接等待期间占用数据库事务或调用模型。
- 浏览器 150ms 合并连续提示、忽略重复 update，重连校准；每 5 秒检查连接活性，25 秒没有提示或心跳即视作半开，关闭旧连接；SSE 不可用时每 5 秒轮询并每 5 秒重试连接。旧连接的迟到事件不能干扰新连接。终态最终读取最多 3 次，完成后清理。连接成功不是可靠消费确认，也不承诺恰好一次投递。
- 所有 fetch / EventSource 集中在 api.ts。人工写命令仍为显式 POST，绑定最新 Run version 和原有 revision/hash/review_version。责任声明与未预选确认必填；不会通过 SSE 自动批准。
- REST 采用请求序号、Run ID 和非递减版本守卫；读取失败隐藏旧投影上的写操作。新版本清空旧审批/修订输入和确认。命令已受理而读取失败时保留 Run ID 并提示先查结果，不盲目重发。

默认脚本启动的旧进程不会因源码变化自动升级；更新后需重启 API。真实 Provider 的模型效果仍须独立评测，工作台通过不表示文档业务语义已获保证。


## 正式产物下载与统一运行（模块五收尾）

已完成并具有当前审批、人工正文审阅、终审和 Artifact 证据的 Run，在工作台的“正式交付物”区显示三个下载按钮：PRD.md、TD.md、DeliverySpec.json。历史 completed Run 若缺少当前证据会拒绝导出，不补造历史审批或终审。

`GET /api/runs/{run_id}/artifacts/{kind}?revision=N&content_hash=...` 的 kind 只接受 prd、td、delivery_spec。下载绑定服务端清单中的 revision/Hash，未知类型、旧版本/Hash、未发布 Run 或证据损坏明确拒绝。服务端重新核对全部发布证据，从批准 Revision 及冻结 DeliverySpec 序列化产生精确 UTF-8 字节；固定文件名，无客户端文件路径读取。响应 attachment、no-store、ETag 与 X-Content-SHA256，文件字节 Hash 与 ArtifactRef/审批一致。下载不调用模型、不推进 Run。

统一启动：

```bash
bash scripts/start-scaffold.sh
```

可指定端口查找起点及数据库：

```bash
API_PORT=8790 WEB_PORT=5190 SPECCRAFT_DB_PATH=/绝对路径/runs.sqlite3 bash scripts/start-scaffold.sh
```

端口被占用时向后最多检查 100 个候选，绝不按端口杀进程；Web 使用 strictPort。监督器只管理本次创建的独立子进程组，退出清理 API、Web 及其子进程；子服务异常退出时停止本次其他服务。既有 CodePilot 或其他项目进程不受影响。API 有界优雅退出，避免 SSE 连接阻塞停止。

Worker 的 `SPECCRAFT_START_WORKER`：

- `auto`（默认）：专用 DeepSeek 配置合法时启动；缺失或无效时明确显示 Worker 未启动及配置名称，API/Web 仍可用于显式 Fake 教学或已发布产物读取。managed 模型请求不会静默回退 Fake。
- `1`：要求后台 Worker；缺少配置则整个启动拒绝、退出 2。
- `0`：明确不启动 Worker。

`GET /api/runtime` 返回监督器的脱敏运行元数据，网页后台模式每 5 秒读取 Worker 状态。running/disabled/exited/stale/unknown 区分显示，父进程超过 10 秒未更新则 stale；独立手工启动 API 时 unknown，并非伪称 Worker 在线。状态不包含凭据，也不代替领域事实或审批。运行元数据写在本实例私有临时目录，关闭后回收，不入库或提交。

真实 DeepSeek 连通性、远端协议及匿名样例内容质量仍需专用配置单独验收；HTTP 替身、浏览器操作或测试通过均不能代替真实效果。
