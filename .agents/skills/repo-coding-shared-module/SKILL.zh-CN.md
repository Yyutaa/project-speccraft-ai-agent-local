---
name: repo-coding-shared-module
description: 查找并应用本仓库的共享包使用、归属和跨应用影响规则。
---

# 仓库编码：共享模块

## 用途

在提议共享模块改动之前，先确认是否存在真正的前端共享包。

## 上下文读取

- 读取 `AGENTS.md` 了解 Repo Guide 入口信息。
- 读取 `repo-profile.md` 中相关的稳定事实、修改边界、命令、共享包范围、应用运行时拓扑和应用到包依赖映射章节。
- 只在需要证据时检查当前仓库源码。

## 证据入口

- 轻量采样中未找到证据
- `packages/contracts`、`packages/agent-kernel` 和 `packages/speccraft` 是 Python 后端包；`apps/web` 没有 JavaScript 共享包，也没有导入 `packages/*`。
- 这些采样路径只是证据入口，不是全局强制实现规则。当同应用、同框架、同模块的当前示例与这些入口不一致时，优先使用当前示例。
- 除非用户明确确认这些路径为稳定的仓库级约束，否则只把它们当作查找锚点，而不是强制全局规则。

## 按框架查找

- React：没有前端共享包；检查 `apps/web/src` 的导入以确认不存在跨包依赖。
- Vue：轻量采样中未找到证据
- H5：轻量采样中未找到证据

## 需要检查的内容

- `apps/web/src/App.tsx` 和治理组件的导入
- `apps/web/package.json` 依赖

## 需要避免的内容

- 把 Python 后端包当作前端共享模块
- 未经确认新建共享包
- 在前端范围内改动后端契约代码

## 需要确认

- 是否真的需要前端共享包
- 改动是否应归入 Python 后端范围

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
- 当前不存在前端共享包层；不要臆造。
