---
name: repo-coding-menu
description: 查找并应用本仓库的菜单、导航、侧边栏与门户入口规则。
---

# 仓库编码：菜单

## 用途

在修改阶段导航、工作台导航或门户入口行为之前，先定位仓库真实的导航或菜单承载面。

## 上下文读取

- 读取 `AGENTS.md` 了解 Repo Guide 入口信息。
- 读取 `repo-profile.md` 中相关的稳定事实、修改边界、命令、共享包范围、应用运行时拓扑和应用到包依赖映射章节。
- 只在需要证据时检查当前仓库源码。

## 证据入口

- React：`apps/web/src/App.tsx`
- React：`apps/web/src/main.tsx`
- 仓库没有菜单、侧边栏、门户入口或 router 配置；导航由单个 `App` 组件内联渲染。
- 这些采样路径只是证据入口，不是全局强制实现规则。当同应用、同框架、同模块的当前示例与这些入口不一致时，优先使用当前示例。
- 除非用户明确确认这些路径为稳定的仓库级约束，否则只把它们当作查找锚点，而不是强制全局规则。

## 按框架查找

- React：检查 `apps/web/src/App.tsx` 的阶段/工作台渲染；这里没有可扩展的菜单注册层。
- Vue：轻量采样中未找到证据
- H5：轻量采样中未找到证据

## 需要检查的内容

- `apps/web/src/App.tsx` 的阶段展示和命令可见性
- 新增导航入口前对 `Run.available_commands` 的处理

## 需要避免的内容

- 臆造不存在的侧边栏或门户配置
- 让客户端导航决定工作流阶段

## 需要确认

- 是否真的需要新的导航承载面
- 改动属于工作流阶段还是真实菜单项

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
- 菜单或导航状态必须跟随服务端投影，不能由客户端自编工作流逻辑。
