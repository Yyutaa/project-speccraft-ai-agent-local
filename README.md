# SpecCraft AI Agent

SpecCraft 是一个个人开发项目，用于探索本地优先、契约驱动的 AI 需求分析与研发规格编制。目标是把需求整理为经过人工确认的 `PRD.md`、`TD.md` 和机器可读的交付规格。

当前仓库仍是教学脚手架，完整领域工作流正在逐步实现。Run 从可信来源和只读仓库上下文开始，经 Fact Ledger、确定性五维完整度 Gate 与人工澄清后，构建并冻结 PRD。获批 PRD 单向派生八类 Design Authority 和统一 TD Blueprint；确定性 Fake TD Author 使用版本化资源生成 TD，人工批准后发布带版本、Hash 和义务追溯的 DeliverySpec。内存 LangGraph 在澄清、PRD 审阅、技术决定和 TD 审阅处保存人工中断点，由独立用户命令恢复。系统不具备持久化、跨进程恢复、身份认证或真实内容质量保障。

## 当前内容

- React 19、Vite、TypeScript 与 Ant Design 前端壳；
- FastAPI 健康检查、项目状态与最小 Run/审批 API；
- Pydantic Run 请求和响应 Contract；
- Fact/Decision 证据 Contract、Completeness Analyzer、澄清 Batch 与回答 API；
- PRD Blueprint、版本化草稿、局部修订、基础文档就绪检查与绑定内容 Hash 的人工审批；
- 八类 Design Authority、TD Blueprint、统一 TD、技术决定请求和绑定内容 Hash 的人工审批；
- `ArtifactRef`/`ArtifactEnvelope` 与不复制文档正文的机器可读 DeliverySpec；
- 来源快照与只读 Repository Harness：服务端仅绑定匿名 ExportFlow 样例，支持 GUIDE_ONLY / INDEXED_READONLY；
- `speccraft` 中的单进程内存 Runner 与确定性 Fake Provider；
- LangGraph `StateGraph` 与内存 checkpointer：只记录每个 Run 的 Gate 路由游标，不保存文档正文或审批证据；
- `contracts`、`agent-kernel`、`speccraft` Python 包；
- CLI 和 Worker 入口；
- 匿名需求、仓库样例与 PRD/TD 编制资源；
- 前端和后端的基础验证入口。

当前 Run 演示支持内联需求或样例仓库需求文件创建、读取、澄清回答、PRD 局部修订、技术决定以及 PRD/TD 审批。PRD 批准后，确定性代码从冻结章节、权威 Fact 引用和 Harness 构建 Authority 与义务映射；TD 只能选择实现方式。缺少关键技术选择时 Run 暂停等待用户，不能由 Fake Author 自动决定。TD 审批同时绑定 revision、内容 Hash、审批人和理由；成功后才形成三份 Artifact Envelope 和 DeliverySpec。API 进程中的 LangGraph 使用 `thread_id=run_id` 暂停和恢复；图节点不写入领域状态。若命令已提交而检查点同步失败，API 返回 `503 workflow_sync_pending` 与 `committed=true`，客户端应先读取 Run 再继续操作，不应重发原命令。进程重启会清空全部 Run 与检查点，所有身份字段仍是用户提交文本。

## 计划中的能力

- 以共享 Contract 定义稳定输入、产物和阶段结果；
- 实现持久化 Run、Artifact、审批与恢复；
- Issue-driven TD 质量闭环；
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
