---
name: repo-coding-template-dialog
description: 查找并应用本仓库的模态框、抽屉、确认和批量操作弹窗模板。
---

# 仓库编码：弹窗模板

## 用途

在新增模态框、抽屉或确认流程之前，先找到最接近的同应用弹窗示例。

## 上下文读取

- 读取 `AGENTS.md` 了解 Repo Guide 入口信息。
- 读取 `repo-profile.md` 中相关的稳定事实、修改边界、命令、共享包范围、应用运行时拓扑和应用到包依赖映射章节。
- 只在需要证据时检查当前仓库源码。

## 证据入口

- 轻量采样中未找到证据
- 未发现 `Modal`、`Drawer` 或确认弹窗用法；`antd` 已安装，是组件库起点。
- 这些采样路径只是证据入口，不是全局强制实现规则。当同应用、同框架、同模块的当前示例与这些入口不一致时，优先使用当前示例。
- 除非用户明确确认这些路径为稳定的仓库级约束，否则只把它们当作查找锚点，而不是强制全局规则。

## 按框架查找

- React：没有同应用弹窗示例；从 Ant Design `Modal` 或 `Drawer` 开始，并与用户确认放置位置。
- Vue：轻量采样中未找到证据
- H5：轻量采样中未找到证据

## 需要检查的内容

- `apps/web/src/App.tsx` 中现有的内联确认模式
- `apps/web/package.json` 中可用的组件库

## 需要避免的内容

- 手写模态框或抽屉 UI
- 假设已存在弹窗层
- 把整页工作流步骤做成弹窗

## 需要确认

- 不存在同应用弹窗模板；需确认位置和触发方式
- 流程应为弹窗还是整页

## 验证提示

- `npm --prefix apps/web run typecheck`
- `npm --prefix apps/web run test`
- `npm --prefix apps/web run build`

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
- 优先使用有证据的组件库（Ant Design）；内联示意仅作 fallback。

## React 结构示意

这里只是结构示意，不是可直接复制的代码。

```text
apps/web/src/<dialog-module>/
  dialog.tsx       # Ant Design Modal/Drawer 封装
  content.tsx      # 表单或确认内容
```

- 组件库优先：Ant Design `Modal`、`Drawer`、`Button`、`Space`。
- 关联规则技能：`repo-coding-components`、`repo-coding-template-form-page`、`repo-coding-error-code`。

## H5 结构示意

这里只是结构示意，不是可直接复制的代码。本仓库不存在 H5 面。

```text
apps/web/src/<mobile-dialog-module>/
  sheet.tsx        # Ant Design Mobile Popup 占位
```

## 模板应用规则

- 依据 `repo-profile.md` 确认目标应用、根目录和框架。
- 优先使用同应用、同框架示例和有证据的组件库用法，而不是内联结构示意。
- 不要把自定义手写表格、表单、弹窗、抽屉、列表或底部面板作为默认实现。
- 模板来源优先级：
  1. 用户提供的参考模块。
  2. 当前源码中发现的同应用、同框架、同页面/弹窗类型示例。
  3. 目标仓库有证据的组件库模式。
  4. 本技能中的 React/H5 内联结构示意。
- 只有当目标框架是 React 或 H5 且没有更高优先级参考时，才使用内联模板。
- 对 Vue 目标，不要使用 React/H5 内联模板；检查同应用 Vue 示例并标注 `Requires Confirmation`。
- 在检查同应用示例和有证据的组件库用法之前，不要直接复制内联结构示意。
- 如果内联结构示意与更高优先级参考冲突，以更高优先级参考为准并报告冲突。
