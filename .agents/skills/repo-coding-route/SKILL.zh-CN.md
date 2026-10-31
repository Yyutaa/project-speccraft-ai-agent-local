---
name: repo-coding-route
description: 查找并应用本仓库的路由注册、页面入口和路由参数规则。
---

# 仓库编码：路由

## 用途

在新增路由或路由参数之前，先定位真实的页面入口与挂载面。

## 上下文读取

- 读取 `AGENTS.md` 了解 Repo Guide 入口信息。
- 读取 `repo-profile.md` 中相关的稳定事实、修改边界、命令、共享包范围、应用运行时拓扑和应用到包依赖映射章节。
- 只在需要证据时检查当前仓库源码。

## 证据入口

- React：`apps/web/src/main.tsx`
- React：`apps/web/src/App.tsx`
- 仓库没有 router 包或路由表；`main.tsx` 直接挂载 `App`。
- 这些采样路径只是证据入口，不是全局强制实现规则。当同应用、同框架、同模块的当前示例与这些入口不一致时，优先使用当前示例。
- 除非用户明确确认这些路径为稳定的仓库级约束，否则只把它们当作查找锚点，而不是强制全局规则。

## 按框架查找

- React：`apps/web/src/main.tsx` 直接挂载单个 `App` 入口；不存在路由注册表。
- Vue：轻量采样中未找到证据
- H5：轻量采样中未找到证据

## 需要检查的内容

- `apps/web/src/main.tsx` 和 `apps/web/src/App.tsx`
- 如果涉及路径或代理变化，检查 `apps/web/vite.config.ts`

## 需要避免的内容

- 未经确认就引入 `react-router` 或路由表
- 因为其他前端有路由层就假设本仓库也有

## 需要确认

- 是否要引入新的路由层
- 是否把应用内阶段误当成路由

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
- 除非用户明确要求路由，否则不要把工作流阶段当作 URL 路由。
