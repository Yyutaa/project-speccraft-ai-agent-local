# SpecCraft AI Agent 协作约定

## 项目定位

本仓库是个人开发的 SpecCraft AI Agent 教学项目，目前处于分阶段实现阶段。当前包含共享 Run Contract、同步单进程内存 Runner、内存 LangGraph 人工中断/恢复、确定性 Fake Author、PRD Blueprint 与人工冻结，以及从批准 PRD 单向派生的 Design Authority、统一 TD 和 DeliverySpec；持久化、真实 Provider、完整质量 Workflow、Worker、质量闭环和 Codex 插件尚未实现。

按当前能力边界逐步开发，完成验收并记录可复现的证据。

## 开工前读取

1. 本文件；
2. `README.md`；
3. 涉及 Web 时读取 `DESIGN.md`；
4. 涉及 FastAPI 时读取 `.agents/skills/fastapi/SKILL.md`。

开始修改前运行 `git status --short --branch`，不要覆盖已有改动。

## 固定产品边界

目标能力是 P0 Contract、P1 Shared Kernel、P2 Provider-driven SpecCraft 与 P2.5 Codex Native。正式产物为：

```text
PRD.md
TD.md
DeliverySpec.json
```

面向用户的八阶段流程固定为：

```text
需求上下文构建
→ 需求澄清与决策
→ 产品规格设计
→ 产品规格验收
→ 技术方案设计
→ 技术方案验证
→ 技术方案验收
→ 交付物发布
```

PRD 必须先批准冻结，TD 不得回写已批准 PRD。模型不得代替用户批准 PRD、TD 或发布结果。

## 当前代码边界

- `apps/api/`：提供健康检查、静态项目状态以及内存 Run 的创建、读取、澄清、PRD 局部修订、技术决定与 PRD/TD 审批 API。
- `apps/web/`：展示静态八阶段路线，并通过 API 创建、修订、审批和观察一个 Run；状态与可用命令来自服务端响应。
- `apps/cli/`：只显示项目状态。
- `apps/worker/`：只说明 Worker 尚未实现。
- `packages/contracts/`：定义共享 Pydantic 请求、响应、Run 状态、PRD/TD Blueprint、Authority、Revision/Approval、Artifact 和 DeliverySpec 契约。
- `packages/agent-kernel/`：只保留包边界。
- `packages/speccraft/`：包含最小内存 Runner、只保存路由游标的 LangGraph 协调器、确定性 Authority/Blueprint 构建与 Fake Author，不实现持久化或完整质量 Workflow。
- `examples/speccraft/`：匿名输入样例，不是预期输出。
- `learning-assets/`：PRD 模板、指南和自检是当前 PRD 编制输入；其他资源仍不代表已实现能力。

## 实现规则

- Python 3.12；生产代码使用类型注解。
- 后端按 `domain → application → ports/adapters → composition root` 单向依赖。
- 前端不复制 Workflow、Policy 或质量决策，只展示后端投影。
- 输入路径必须规范化并限制在允许根目录内。
- 优先使用标准库和已有依赖；新依赖必须对应明确需求。
- 不提交 `.venv/`、`node_modules/`、缓存、构建产物、数据库、`.env` 或模型凭据。
- 不提交真实业务 PRD、未脱敏日志、完整对话或模型推理过程。
- 后续生成的 PRD、TD、技术方案、需求分析和 Handoff Markdown 统一放在根目录 `docs/`；该目录是本地资料，整体不提交到 Git。稳定的项目协作约定仍写入本文件，面向仓库使用者的公开说明写入 `README.md`。
- 非平凡状态转换、Gate、路径安全和 Artifact 行为必须有正例与负例测试。
- Agent 的完成声明不是证据；报告实际执行命令、退出码和结果。

## 契约、事实源与控制权

- 分层依赖保持单向：Execution Host → SpecCraft Domain → Shared Kernel → Contract；SpecCraft Domain 可直接依赖 Contract。Contract 定义共享数据协议，Kernel 提供通用生命周期机制，SpecCraft Domain 持有产品阶段规则，Host 负责组合入口和适配器。
- 后端领域/内核状态是 Run、Decision、Approval 与 Artifact 的权威事实源。前端只展示服务端投影；Snapshot 是读取投影，Checkpoint 是恢复材料，两者都不能取代或覆盖事实源。
- Source 只表明证据出处，不自动成为已确认 Fact。Fact 必须保留来源和确认状态；Decision 与 Approval 必须能追溯责任主体及其对象版本。
- 模型只提供语义候选、草稿或建议；确定性代码负责结构校验、Gate 和合法状态转换；用户负责产品/技术决策以及 PRD、TD 和发布批准。模型不得批准、发布或将候选直接升级为事实。
- PRD 获批后冻结；TD 只能基于获批 PRD 派生，不得回写 PRD。阶段越界、非法状态和版本冲突必须明确拒绝且不得留下部分状态变化，并由正例与失败用例覆盖。
- 阶段 01 冻结的流程顺序是先批准 PRD，再生成/批准 TD，最后发布 DeliverySpec；阶段 01 可采用内存实现，但不得声称内存状态可跨进程恢复。
- 阶段 01 的 Runner 只保存在单个 API 进程内并同步执行；API 写操作不承诺幂等，Approval 必须绑定正在批准的草稿 revision，重复或越序审批应拒绝且不得改变 Run。
- Fake Provider 只生成可重复的示例草稿，不代表模型能力或内容质量验证；页面不得乐观修改 Run 状态，只能渲染 API 返回值及其 `available_commands`。
- Repository Harness 的允许根目录由服务端组合入口配置，客户端只能提交根内相对来源路径，不能自行授权任意本机路径；目标仓库读取必须只读。
- SourceSnapshot 保留来源类型、规范化相对路径、成功读取状态、原始 UTF-8 内容与其 SHA-256。文件来源在安全读取后、需求文本整理前计算 Hash；需求正文与 Harness 工程上下文保持分离。
- HarnessContextSlice 只包含显式选择的有限文本切片、来源 Hash 与选择理由；切片 Hash 对有序条目及内容执行确定性序列化后计算。仓库工程约束不能升级为产品 Fact 或改写需求。
- 仓库路径必须拒绝穿越、符号链接、敏感/缓存目录、非文本和超限文件；读取失败返回稳定错误码，Run 创建不得留下部分状态。路径安全及过滤行为须同时覆盖成功与拒绝测试。
- Harness 错误码由共享 Contract 枚举定义；API 可映射 HTTP 状态，但不得改写错误码语义。
- `FACT` 必须绑定 SourceSnapshot 的 Hash 与原文摘录；`DECISION` 必须绑定用户澄清命令、问题、批次和账本 revision。推荐项属于提案，不进入权威 Ledger，也不能自动消除 Gap。
- 五个必需维度（角色、流程、权限、失败、验收）缺失或冲突时，确定性 Completeness Gate 必须暂停 PRD 生成；分析器不得调用模型或从自由文本猜测维度完整性。
- 下游规格生成只读取 Fact Ledger 的权威视图；同维度用户 Decision 覆盖冲突来源事实。页面只显示服务端 Run/账本投影，并以独立用户命令提交答案。
- 澄清答案必须完整覆盖当前阻塞问题并匹配 `expected_revision`；内存 Runner 对每个 Run 拒绝重复 `command_id`。任何失败不得留下部分账本、Run 或 Artifact 更新。
- PRD Blueprint 由确定性代码从 Ledger 权威 Fact/Decision 构建，必须覆盖全部权威 fact ID；它只规划章节、适用性和引用，不含正文，也不设独立人工 Gate。
- PRD Author 只能接收 Blueprint 引用的权威 claim 与版本化编制资源；基础就绪检查只判断标题、章节、顺序、空内容和占位符，不证明业务正确性，也不触发自动修复循环。
- PRD 局部修订必须指明单个章节、用户反馈、当前 revision 与精确内容 SHA-256；每次成功修订产生新 revision 并重新执行基础检查。旧版本或旧 Hash 的命令须拒绝且不得更改 Run。
- PRD 审批是独立人工命令，receipt 绑定当前 revision、精确内容 Hash、actor、rationale 和时间。审批后 PRD 不可变；前端只投影就绪结果、可用命令和审批证据。
- Design Authority 只能从当前获批 PRD、其权威 Fact 引用和只读 Harness 约束单向派生，固定覆盖 API、数据、错误、幂等、权限、状态、失败和非功能八类主题；TD 不得反向改写 PRD。
- TD Blueprint 必须覆盖全部 Authority ID 与冻结 PRD 义务，并把它们映射到统一 TD 章节。技术信息不足时形成独立技术决定请求，由用户回答；技术决定不能升级为产品 Fact 或改变角色、权限、流程和验收承诺。
- TD Revision 必须绑定获批 PRD revision/hash、Authority Pack hash 和冻结义务快照。确定性校验负责版本、引用和结构化义务一致性；自由文本语义正确性仍由人工审阅。
- TD 审批 receipt 绑定当前 revision、精确内容 Hash、actor、rationale 和时间。只有 TD 批准后才能发布 PRD、TD 与 DeliverySpec 三份正式产物。
- ArtifactRef/Envelope 保存类型、版本、内容 Hash 与派生关系；正文留在文档 Revision 中。DeliverySpec 是不复制 PRD/TD Markdown 正文的机器交接投影，所有引用必须指向获批版本和 Hash。
- LangGraph 每个 Run 使用固定 `thread_id=run_id`，只保存 `run_id`、当前人工 Gate 与绑定权威版本的路由标识；Runner 中的 Run、Ledger、Revision、Approval 和 Artifact 始终是事实源。图节点不得在 `interrupt()` 前执行领域写入，恢复时可重放的节点只读取权威 Run 并路由。
- 独立用户命令先由 Runner 完成既有 Gate、版本、Hash 与重复命令校验，成功提交后才恢复图。PRD 局部修订重新停在 PRD 审阅 Gate；技术决定 Gate 仅在 Runner 明确请求时出现。已有 Run 的检查点缺失或与 Run 失同步时写命令须关闭，不得自动重建检查点放行；若领域命令已提交而图更新失败，API 必须明确报告 `committed=true`，客户端先读取 Run，不得盲目重发命令。读取失败时前端不得继续展示旧投影的写操作。
- 当前图与 Runner 均只存在于同一 API 进程内；进程重启后两者同时丢失，不提供跨进程恢复。检查点不能代替人工审批证据或文档正文。

## 验证

基础验证：

```bash
make verify
```

涉及前端时额外关注浏览器中的真实状态和网络请求。
