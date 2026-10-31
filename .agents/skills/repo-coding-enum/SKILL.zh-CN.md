---
name: repo-coding-enum
description: 查找并应用本仓库的枚举来源、选项映射和状态展示规则。
---

# 仓库编码：枚举

## 用途

让联合类型和展示标签来自现有共享定义，而不是重复字面量。

## 上下文读取

- 读取 `AGENTS.md` 了解 Repo Guide 入口信息。
- 读取 `repo-profile.md` 中相关的稳定事实、修改边界、命令、共享包范围、应用运行时拓扑和应用到包依赖映射章节。
- 只在需要证据时检查当前仓库源码。

## 证据入口

- React：`apps/web/src/governance.ts`
- React：`apps/web/src/api.ts`
- `governance.ts` 定义 `dimensionLabels` 和 `dimensionOptions`；`api.ts` 定义共享联合类型。
- 这些采样路径只是证据入口，不是全局强制实现规则。当同应用、同框架、同模块的当前示例与这些入口不一致时，优先使用当前示例。
- 除非用户明确确认这些路径为稳定的仓库级约束，否则只把它们当作查找锚点，而不是强制全局规则。

## 按框架查找

- React：检查 `apps/web/src/governance.ts` 和 `apps/web/src/api.ts` 中的联合类型。
- Vue：轻量采样中未找到证据
- H5：轻量采样中未找到证据

## 需要检查的内容

- `governance.ts` 中的 `dimensionLabels` / `dimensionOptions`
- `api.ts` 中的状态和命令联合类型
- `App.tsx` 中现有标签映射

## 需要避免的内容

- 重复定义标签映射或状态字符串
- 为同一领域概念定义第二套枚举来源

## 需要确认

- 新的共享枚举来源
- 展示标签属于领域还是单个组件

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
- 优先使用现有联合类型和标签映射，而不是新增本地枚举。
