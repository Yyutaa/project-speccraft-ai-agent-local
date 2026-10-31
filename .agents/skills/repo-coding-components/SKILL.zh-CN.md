---
name: repo-coding-components
description: 查找并应用本仓库的应用级组件归属、封装和复用规则。
---

# 仓库编码：组件

## 用途

把组件归属保持在单个 React 应用内，并复用现有基于 Ant Design 的组件模式。

## 上下文读取

- 读取 `AGENTS.md` 了解 Repo Guide 入口信息。
- 读取 `repo-profile.md` 中相关的稳定事实、修改边界、命令、共享包范围、应用运行时拓扑和应用到包依赖映射章节。
- 只在需要证据时检查当前仓库源码。

## 证据入口

- React：`apps/web/src/GovernanceCreate.tsx`
- React：`apps/web/src/GovernanceResolution.tsx`
- React：`apps/web/src/TdGovernance.tsx`
- 这些是与 `App.tsx` 同级的扁平应用级组件，基于 Ant Design 基础组件和 props 构建。
- 这些采样路径只是证据入口，不是全局强制实现规则。当同应用、同框架、同模块的当前示例与这些入口不一致时，优先使用当前示例。
- 除非用户明确确认这些路径为稳定的仓库级约束，否则只把它们当作查找锚点，而不是强制全局规则。

## 按框架查找

- React：在抽取或移动组件前，检查治理组件及其共享字段。
- Vue：轻量采样中未找到证据
- H5：轻量采样中未找到证据

## 需要检查的内容

- `GovernanceCreate.tsx`、`GovernanceResolution.tsx`、`TdGovernance.tsx` 中的组件边界和 props
- `App.tsx` 的 Ant Design 导入
- 请求的 UI 是否已有封装

## 需要避免的内容

- 为应用内组件新建共享包
- 重复实现已有封装
- 用自定义 UI 替换 Ant Design 基础组件

## 需要确认

- 组件是否应在应用内层与共享层之间移动
- 其他位置是否已有类似封装

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
- 在出现真实第二消费者之前，组件归属保持在应用内。
