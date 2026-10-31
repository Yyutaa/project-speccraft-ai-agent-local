# SpecCraft AI Agent

SpecCraft 是一个个人开发项目，用于探索本地优先、契约驱动的 AI 需求分析与研发规格编制。目标是把需求整理为经过人工确认的 `PRD.md`、`TD.md` 和机器可读的交付规格。

当前仓库仍是教学脚手架，完整领域工作流正在逐步实现。Run 从可信来源和只读仓库上下文开始，经来源候选逐项确认、独立知识/假设治理、Fact Ledger、确定性五维完整度 Gate 与人工澄清后，构建并冻结 PRD。获批 PRD 单向派生八类 Design Authority 和统一 TD Blueprint；确定性 Fake TD Author 使用版本化资源生成 TD，经独立人工正文审阅、必要的单章节修订与复查，再由用户批准后发布带版本、Hash 和义务追溯的 DeliverySpec。内存 LangGraph 在澄清、PRD 审阅、技术决定和 TD 审阅处保存人工中断点，由独立用户命令恢复。系统不具备持久化、跨进程恢复、身份认证或真实内容质量保障。

## 当前内容

- React 19、Vite、TypeScript 与 Ant Design 前端壳；
- FastAPI 健康检查、项目状态与最小 Run/审批 API；
- Pydantic Run 请求和响应 Contract；
- 严格来源准入、Fact/Decision 证据、Completeness Analyzer、原子澄清批次与回答 API；
- 有限知识引用、独立假设/上下文冲突及解决证据，参考材料不自动进入产品事实；
- PRD Blueprint、版本化草稿、局部修订、基础文档就绪检查与绑定内容 Hash 的人工审批；
- 八类 Design Authority、TD Blueprint、统一 TD、技术决定请求、TD 正文人工审阅/单章修订及绑定版本/Hash/当前审阅的人工审批；
- `ArtifactRef`/`ArtifactEnvelope` 与不复制文档正文的机器可读 DeliverySpec；
- 来源快照与只读 Repository Harness：服务端仅绑定匿名 ExportFlow 样例，支持 GUIDE_ONLY / INDEXED_READONLY；
- `speccraft` 中的单进程内存 Runner 与确定性 Fake Provider；
- LangGraph `StateGraph` 与内存 checkpointer：只记录每个 Run 的 Gate 路由游标，不保存文档正文或审批证据；
- `contracts`、`agent-kernel`、`speccraft` Python 包；
- CLI 和 Worker 入口；
- 匿名需求、仓库样例与 PRD/TD 编制资源；
- 前端和后端的基础验证入口。

当前 API 支持内联需求或样例需求文件创建、来源确认、澄清回答、PRD 局部修订、技术决定、TD 人工正文审阅、TD 单章节修订及审批。创建后 Ledger 为空，原文不会自动成为 FACT。用户可拒绝原文候选并明确回答角色、流程、权限、失败与验收五维；知识引用与假设留在独立参考区，有产品影响或风险未知的假设必须解决。

PRD 批准后冻结，产品义务只取六类产品章节，背景不自动升级为技术承诺。TD 的结构一致性检查不理解所有正文语义；必须独立记录绑定当前 PRD/TD revision、Hash 与义务的人工审阅。发现冲突会留在同一 TD Gate，修订使旧审阅失效，逐项复查后才能再次批准。产品范围需要改变时创建带可选 parent_run_id 的独立新 Run，不复制旧批准。

PRD/TD/澄清生成器仍为 Fake。输入输出实际经过 typed 任务边界：完整 UTF-8 输入 128 KiB、输出 256 KiB、最多 32 条提案/发现；角色标签和严格结构只限制写入权限，不提供语义正确性或 Prompt Injection 免疫保证。人工姓名、确认和 producer 字段均为责任声明，系统没有身份认证。

API 中的 LangGraph 使用 thread_id=run_id，只保存 Gate 游标；节点不写领域状态。领域已提交而图更新失败时，API 返回 503 workflow_sync_pending 与 committed=true，客户端先读取 Run，不能重发原命令。进程重启清空全部 Run、命令去重记录和检查点，不提供持久恢复。

### 写接口版本

所有 `/api/runs` 写请求必须显式携带 `governance_contract_version: 2`，缺失返回 422 contract_version_required。澄清、TD 审阅和 TD 修订的成功 command_id 在同一 Run 内不可重用；失败不消费 ID。这是重复命令拒绝，不承诺 HTTP 幂等。现有客户端需与服务端同版升级。

```json
{"governance_contract_version": 2, "requirement": "管理员导出报表，访客无权限"}
```

主要命令入口：

| 方法与路径 | 用途 |
| --- | --- |
| POST /api/runs；GET /api/runs/{id} | 创建与读取进程内 Run |
| POST /api/runs/{id}/clarifications/answers | 来源处理、五维答案、假设/冲突一次性解决 |
| POST /api/runs/{id}/prd/revisions；POST /api/runs/{id}/approvals/prd | 单章修订与人工冻结 PRD |
| POST /api/runs/{id}/technical-decisions | 独立提交技术选择 |
| POST /api/runs/{id}/td/reviews；POST /api/runs/{id}/td/revisions | 人工正文审阅、单章修订与复查 |
| POST /api/runs/{id}/approvals/td | 当前有效审阅绑定审批，发布三产物 |

完整请求和错误结构以 FastAPI `/docs` 与共享 Pydantic Contract 为准。服务端只绑定匿名 ExportFlow 样例，知识只能显式选择 `knowledge/` 内受限文本，不提供网络检索。

## 计划中的能力

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
