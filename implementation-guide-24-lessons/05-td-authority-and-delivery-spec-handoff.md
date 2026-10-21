# 阶段 05 Handoff：TD 权威与 DeliverySpec

## 目标与非目标

本阶段已把阶段 01 的自由文本 TD 演示替换为单向、可追溯的技术交付链：批准 PRD 派生八类 Design Authority 和 TD Blueprint，版本化 TD Authoring Pack 生成统一 TD，人工审批后发布 `PRD.md`、`TD.md` 与机器可读 `DeliverySpec.json` 的内存 Artifact 投影。

本阶段没有实现 Issue-driven 质量循环、自动修复、数据库、持久化 Artifact Store、Worker、Web Workbench、真实 Provider、LangGraph 或 Codex 插件。TD 的自然语言业务正确性仍由人工判断。

## 选型理由

- Pydantic、现有 FastAPI/React 和 Python 标准库足以表达结构、Hash 和状态转换，没有新增依赖。
- Authority 与 Blueprint 由确定性代码生成；Fake TD Author 只填充现有统一模板，不能决定产品范围或审批。
- 当前同步内存 Runner 可以清楚展示 Gate、失败原子性与人工控制权，暂不需要 Workflow 框架。
- DeliverySpec 只保存机器需要的 Artifact 引用、Authority Hash 与义务映射，不复制 PRD/TD Markdown 正文。

## 模块边界

- `packages/contracts/src/deliveryflow_contracts/td.py`：八类 Authority、统一 TD 章节、Blueprint、义务、Revision、技术决定和 TD 审批 Contract。
- `packages/contracts/src/deliveryflow_contracts/artifacts.py`：ArtifactRef、Envelope、审批引用和 DeliverySpec Contract。
- `packages/contracts/src/deliveryflow_contracts/runs.py`：技术决定暂停、TD 审批与发布状态不变量。
- `packages/speccraft/src/deliveryflow_speccraft/td.py`：从冻结 PRD 派生 Authority/义务/Blueprint，并校验 PRD→TD 一致性。
- `packages/speccraft/src/deliveryflow_speccraft/td_authoring.py`：加载版本化 TD 编制包，提供最小 Author Port 和确定性 Fake 实现。
- `packages/speccraft/src/deliveryflow_speccraft/runner.py`：在单进程锁内组合派生、技术决定、审批和发布。
- `apps/api/main.py`：公开技术决定和 TD 审批命令，映射稳定错误码。
- `apps/web/src/api.ts`、`App.tsx`：只展示服务端状态、技术决定、TD Hash、审批证据和 DeliverySpec。

## 状态与数据流

```text
批准 PRD revision + content hash
  → 冻结 7 个产品章节义务
  → 确定性派生 8 类 Design Authority
  → TD Blueprint 映射到统一 16 章节
  → TD Authoring Pack + Fake TD Author
      ├─ 信息充分：TD r1 + SHA-256
      └─ 关键取舍不足：td_awaiting_decision → 用户回答 → TD r1
  → PRD/Authority/义务一致性校验
  → 用户提交 TD revision/hash/actor/rationale
  → 发布 PRD、TD、DeliverySpec 三个 Artifact Envelope
  → completed
```

Ledger 和获批 PRD 持有产品事实；Authority 是从获批 PRD 派生的技术输入；TD 可以选择实现方式。技术决定单独保存，不进入产品 Fact Ledger。前端只提交用户命令，不能计算状态、Hash 或发布结果。

## 公开 Contract

- `DesignAuthorityPack` 按固定顺序包含 API、数据、错误、幂等、权限、状态、失败、非功能八类主题，绑定批准 PRD revision/hash，并保留 Fact 与 PRD 章节引用。
- `TdObligation` 冻结非文档信息 PRD 章节的正文、章节 Hash 和 Fact 引用。`TdBlueprint` 必须覆盖全部 Authority ID 和义务 ID，并保持统一 TD 的 16 章节顺序。
- `TdRevision` 绑定自身内容 Hash、批准 PRD revision/hash、Authority Pack Hash 和义务快照。结构化义务被改变、引用旧 PRD 或漏掉追溯 ID 时确定性拒绝。
- `TechnicalDecisionRequest` 只表达无法唯一确定的技术取舍；`POST /api/runs/{run_id}/technical-decisions` 必须完整回答当前请求并绑定当前 PRD revision/hash。
- `POST /api/runs/{run_id}/approvals/td` 接收 revision、content_hash、actor、rationale；receipt 增加 approved_at。旧版本、错误 Hash、越序或重复审批不改变 Run。
- `DeliverySpec` 版本为 1.0，引用获批 PRD/TD ArtifactRef、Authority Pack Hash 和义务到 Authority/TD 章节的映射。它不含 `prd_content` 或 `td_content`。
- Artifact Envelope 保存产物类型、版本、内容 Hash、派生关系、发布时间和相应审批引用；当前仅存在于内存 Run 中。

## 失败与恢复策略

Runner 先在局部变量中完成 Authority、Blueprint、TD 与完整 Run 校验，最后才替换内存快照。合法 PRD 审批先被冻结；TD 改写角色、权限、流程、失败或验收等义务时，TD 审批/发布 Gate 返回 `td_obligation_conflict`，已批准 PRD 不被回滚。错误 TD Hash 返回 `content_hash_conflict`。失败不会形成 TD receipt、DeliverySpec 或 Artifact 的部分发布。

技术决定回答不完整、答案不属于服务端给出的选项、旧 PRD 版本或错误 PRD Hash 会被拒绝。用户可重新读取 Run，以当前服务端投影重新提交。进程重启后没有恢复能力。

## 测试及验收证据

| 命令或验收 | 退出码 | 关键结果 |
| --- | ---: | --- |
| `make verify`（实施前） | 0 | Python 93 项、Web 5 项、lint、mypy 和构建通过 |
| `.venv/bin/python -m pytest -q tests/test_td_contracts.py` | 0 | 4 项；八类 Authority、Blueprint、双 Hash、DeliverySpec 反序列化 |
| `.venv/bin/python -m pytest -q tests/test_td_authority.py` | 0 | 2 项；批准 PRD 确定性派生与旧批准拒绝 |
| `.venv/bin/python -m pytest -q tests/test_td_blueprint.py tests/test_td_authority.py tests/test_td_contracts.py` | 0 | 7 项；Authority/义务章节覆盖 |
| `.venv/bin/python -m pytest -q tests/test_td_authoring.py` | 0 | 2 项；版本化编制包与确定性 Fake Author |
| `.venv/bin/python -m pytest -q tests/test_td_obligations.py` | 0 | 3 项；冻结义务正常、篡改和旧 Hash 负例 |
| `.venv/bin/python -m pytest -q tests/test_td_runner.py` | 0 | 3 项；正常发布、技术决定暂停/恢复、产品范围冲突在发布 Gate 被拒绝且 PRD 保持冻结 |
| 阶段相关 Python 测试集合 | 0 | 26 项通过；TestClient 有既有 Starlette/httpx deprecation warning |
| `.venv/bin/python -m pytest -q` | 0 | 107 项通过，1 个既有 warning |
| `.venv/bin/ruff check apps packages tests` | 0 | 无 lint 错误 |
| `.venv/bin/mypy apps packages/contracts/src packages/agent-kernel/src packages/speccraft/src` | 0 | 23 个源文件无问题 |
| `npm --prefix apps/web run test -- --run` | 0 | Web 5 项通过；TD 审批请求绑定 Hash 和人工证据 |
| `npm --prefix apps/web run typecheck` | 0 | TypeScript 类型检查通过 |
| FastAPI TestClient 手工序列 | 0 | 状态依次为 clarification → PRD approval → TD approval → completed；8 类 Authority、3 个 Artifact、DeliverySpec 1.0；错误 TD Hash 返回 409 且快照不变 |
| 冲突 Author 手工序列 | 0 | PRD 先批准冻结；TD 审批时篡改义务触发 `TdObligationConflict`，TD 未批准、DeliverySpec 未发布且失败前后快照相同 |
| 浏览器 `127.0.0.1:5175` + 临时 API `8766` | 0 | Run `d38c2c93-bf5e-4beb-b9cc-72bb9a544fb0` 完成澄清、PRD/TD 人工审批；页面显示 TD Hash、审批证据与 DeliverySpec 1.0；API 请求为 201/200/200/200 |
| 首次最终 `make verify` | 2 | Python 107 项通过后 Ruff 发现重构遗留的一个未使用 `TdBlueprint` 导入；删除该导入后重跑完整验证 |
| 最终 `make verify` | 0 | Python 107 项、Ruff、mypy 23 个源文件、Web 5 项和 Vite 构建全部通过 |

浏览器验收使用独立临时端口，完成后已停止；原 5174/8765 旧服务没有重启或丢失其内存 Run。

## 已知限制与当前系统快照

- Run、技术决定、Revision、Approval 和 Artifact 仍只在单个 API 进程内；没有持久化、跨进程恢复或强身份认证。
- Authority 可靠绑定批准 PRD 的结构化来源和章节原文，但不能证明任意自然语言 TD 不含隐式语义冲突；人工 TD 审批仍是最终内容 Gate。
- 当前 Fact Ledger 没有模型事实抽取，原始需求常需用户回答五个确定性澄清问题。
- Fake TD Author 只证明契约和状态链路，不代表真实技术设计质量。没有自动质量修复或 Issue Ledger。
- Artifact Envelope 是内存元数据；没有文件下载、对象存储、签名或长期 URI。
- 学习导航所列课程“第 11 章”和“第 12 章”原文未在仓库中找到；本阶段没有把阶段 11 指南误当作课程章节。

## 下一阶段冻结契约

- PRD→Design Authority→TD 为单向依赖；TD 不得反写批准 PRD。
- 八类 Authority、统一 16 章节 TD、PRD 义务全覆盖和版本/Hash 绑定保持稳定。
- 技术决定由用户控制并与产品 Fact/Decision 分离；模型或 Fake Author 不得自动批准或升级事实。
- TD 审批绑定 revision、Hash、actor、rationale 和时间；发布必须发生在审批后。
- DeliverySpec 保持机器投影，不复制 PRD/TD 正文；Artifact 引用绑定批准版本和 Hash。
- 下一阶段质量验证可以读取上述冻结对象并产生 Issue，但不能修改其事实源或绕过人工 Gate。
