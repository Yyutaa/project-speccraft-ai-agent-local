---
name: repo-coding-error-code
description: 查找并应用本仓库的错误码解析、消息映射和兼容性规则。
---

# 仓库编码：错误码

## 用途

处理稳定的 API 错误码和工作流专用失败语义，不要另造一套错误分类。

## 上下文读取

- 读取 `AGENTS.md` 了解 Repo Guide 入口信息。
- 读取 `repo-profile.md` 中相关的稳定事实、修改边界、命令、共享包范围、应用运行时拓扑和应用到包依赖映射章节。
- 只在需要证据时检查当前仓库源码。

## 证据入口

- React：`apps/web/src/api.ts`
- React：`apps/web/src/App.tsx`
- `api.ts` 解析 `workflow_sync_pending` 的 `detail.code`；`App.tsx` 渲染请求错误和已提交命令提示。
- 这些采样路径只是证据入口，不是全局强制实现规则。当同应用、同框架、同模块的当前示例与这些入口不一致时，优先使用当前示例。
- 除非用户明确确认这些路径为稳定的仓库级约束，否则只把它们当作查找锚点，而不是强制全局规则。

## 按框架查找

- React：检查 `apps/web/src/api.ts` 的错误解析和 `apps/web/src/App.tsx` 的错误渲染。
- Vue：轻量采样中未找到证据
- H5：轻量采样中未找到证据

## 需要检查的内容

- `api.ts` 中 `detail.code` 的处理和状态判断
- `App.tsx` 中用户可见错误文本和输入保留

## 需要避免的内容

- 匹配共享契约未定义的错误码字符串
- 吞掉 `503` 工作流同步失败
- 臆造仅客户端使用的错误码

## 需要确认

- 新的错误码族或后端契约变化
- 错误应当阻塞还是仅提示

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
- 错误码属于契约事实；前端可以映射为 UI 状态，但不能重新定义其含义。
