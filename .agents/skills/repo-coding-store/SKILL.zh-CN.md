---
name: repo-coding-store
description: 查找并应用本仓库的状态管理、store 边界和状态归属规则。
---

# 仓库编码：状态管理

## 用途

在移动或共享状态之前，先识别真实的状态归属模型。

## 上下文读取

- 读取 `AGENTS.md` 了解 Repo Guide 入口信息。
- 读取 `repo-profile.md` 中相关的稳定事实、修改边界、命令、共享包范围、应用运行时拓扑和应用到包依赖映射章节。
- 只在需要证据时检查当前仓库源码。

## 证据入口

- React：`apps/web/src/App.tsx`
- React：`apps/web/src/TdGovernance.tsx`
- 状态使用本地 React `useState`；未安装或导入 Redux、Zustand 等 store 库。
- 这些采样路径只是证据入口，不是全局强制实现规则。当同应用、同框架、同模块的当前示例与这些入口不一致时，优先使用当前示例。
- 除非用户明确确认这些路径为稳定的仓库级约束，否则只把它们当作查找锚点，而不是强制全局规则。

## 按框架查找

- React：检查 `apps/web/src/App.tsx` 的 `useState` 用法和治理组件中的本地表单状态。
- Vue：轻量采样中未找到证据
- H5：轻量采样中未找到证据

## 需要检查的内容

- `App.tsx` 中 `useState` / `useEffect` 的边界
- 传入 `GovernanceCreate`、`GovernanceResolution` 和 `TdGovernance` 的 props 流
- 作为权威状态来源的 `Run` 响应

## 需要避免的内容

- 未经确认引入全局 store
- 在客户端派生状态中复制服务端 Run 状态
- 把工作流状态所有权搬到浏览器

## 需要确认

- 状态是否必须跨组件共享
- 新增 store 依赖是否有充分理由

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
- 最窄的状态是组件本地状态；只有证明需要跨组件共享时才升级。
