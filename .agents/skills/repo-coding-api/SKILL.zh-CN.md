---
name: repo-coding-api
description: 查找并应用本仓库的 API 客户端、请求封装、响应处理和类型化契约规则。
---

# 仓库编码：API

## 用途

把前端网络访问保持在现有请求封装内，并保留服务端投影的响应语义。

## 上下文读取

- 读取 `AGENTS.md` 了解 Repo Guide 入口信息。
- 读取 `repo-profile.md` 中相关的稳定事实、修改边界、命令、共享包范围、应用运行时拓扑和应用到包依赖映射章节。
- 只在需要证据时检查当前仓库源码。

## 证据入口

- React：`apps/web/src/api.ts`
- React：`apps/web/vite.config.ts`
- `api.ts` 持有 `fetch` 封装、类型化请求/响应类型和 `WorkflowSyncPendingError`；Vite 代理把 `/api` 转发到 FastAPI。
- 这些采样路径只是证据入口，不是全局强制实现规则。当同应用、同框架、同模块的当前示例与这些入口不一致时，优先使用当前示例。
- 除非用户明确确认这些路径为稳定的仓库级约束，否则只把它们当作查找锚点，而不是强制全局规则。

## 按框架查找

- React：先检查 `apps/web/src/api.ts`；它是唯一的 HTTP 边界。
- Vue：轻量采样中未找到证据
- H5：轻量采样中未找到证据

## 需要检查的内容

- `apps/web/src/api.ts` 的请求封装和错误解析
- `apps/web/src/App.tsx` 的响应到状态投影
- `apps/web/vite.config.ts` 的代理目标

## 需要避免的内容

- 在 `api.ts` 之外新增第二套 HTTP client 或直接 `fetch`
- 在浏览器里自行推导工作流状态而不是读取 Run 响应
- 写命令成功后乐观修改 Run 状态

## 需要确认

- 新的 API 边界或契约版本
- 任何涉及 `workflow_sync_pending` / `committed=true` 处理的改动

## 验证提示

- `npm --prefix apps/web run typecheck`
- `npm --prefix apps/web run test`

## 响应建议

使用自然语言文本。可选轻量标签包括：

- Summary
- Evidence
- Confidence
- Warnings
- Stop Reasons
- Requires Confirmation
- Update Suggestions

## 约束

- 不要把运行时扫描结果写入 `AGENTS.md` 或 `repo-profile.md`。
- 优先使用当前源码证据，而不是过期假设。
- 归属、跨团队范围或低置信度推断不明确时，放入 `Requires Confirmation`。
- 除非用户明确要求实现改动，否则保持原始源码不变。
- 保留 `committed=true` 恢复语义：重新读取 Run，绝不重发命令。
- 不要把后端契约逻辑搬到前端。
