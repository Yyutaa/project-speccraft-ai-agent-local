---
name: repo-coding-hooks
description: 查找并应用本仓库的 hook 组织、请求 hook 和副作用规则。
---

# 仓库编码：Hooks

## 用途

在抽取副作用逻辑之前，先确认是否已有或确实需要可复用 hook。

## 上下文读取

- 读取 `AGENTS.md` 了解 Repo Guide 入口信息。
- 读取 `repo-profile.md` 中相关的稳定事实、修改边界、命令、共享包范围、应用运行时拓扑和应用到包依赖映射章节。
- 只在需要证据时检查当前仓库源码。

## 证据入口

- 轻量采样中未找到证据
- 未发现自定义 hooks 目录或 `use*` 辅助函数；`App.tsx` 使用内联 `useEffect` / `useState`。
- 这些采样路径只是证据入口，不是全局强制实现规则。当同应用、同框架、同模块的当前示例与这些入口不一致时，优先使用当前示例。
- 除非用户明确确认这些路径为稳定的仓库级约束，否则只把它们当作查找锚点，而不是强制全局规则。

## 按框架查找

- React：无自定义 hook 证据；当改动涉及 `apps/web/src/App.tsx` 的内联 effect 时再检查。
- Vue：轻量采样中未找到证据
- H5：轻量采样中未找到证据

## 需要检查的内容

- `App.tsx` 中的 `useEffect` 块
- 同一副作用是否在多个治理组件中重复

## 需要避免的内容

- 没有第二个真实消费者就抽取 hook
- 为替代一个小 effect 而引入状态或取数库

## 需要确认

- hook 是否需要跨组件共享
- 该副作用是否属于应放在服务端的工作流逻辑

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
- 不要把服务端权威工作流行为搬进客户端 hook。
