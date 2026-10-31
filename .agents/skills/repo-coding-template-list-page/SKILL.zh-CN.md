---
name: repo-coding-template-list-page
description: 查找并应用本仓库的列表、表格、搜索和分页页面模板。
---

# 仓库编码：列表页模板

## 用途

在新建列表页之前，先找到最接近的同应用列表或表格示例。

## 上下文读取

- 读取 `AGENTS.md` 了解 Repo Guide 入口信息。
- 读取 `repo-profile.md` 中相关的稳定事实、修改边界、命令、共享包范围、应用运行时拓扑和应用到包依赖映射章节。
- 只在需要证据时检查当前仓库源码。

## 证据入口

- 轻量采样中未找到证据
- 未发现列表、表格、搜索或分页页面；应用是单个 Run 工作台。
- 这些采样路径只是证据入口，不是全局强制实现规则。当同应用、同框架、同模块的当前示例与这些入口不一致时，优先使用当前示例。
- 除非用户明确确认这些路径为稳定的仓库级约束，否则只把它们当作查找锚点，而不是强制全局规则。

## 按框架查找

- React：没有同应用列表模板；`apps/web/package.json` 已安装 `antd`，应作为组件库起点。
- Vue：轻量采样中未找到证据
- H5：轻量采样中未找到证据

## 需要检查的内容

- `apps/web/src/App.tsx` 中现有的重复项渲染
- `apps/web/package.json` 中可用的组件库

## 需要避免的内容

- 手写表格、搜索或分页 UI 而不用 Ant Design
- 假设已存在列表模板
- 请求是单条详情表单却实现列表页

## 需要确认

- 不存在同应用列表模板；需确认页面结构
- 请求的页面是否真的是列表

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
apps/web/src/<list-module>/
  index.tsx        # 页面入口，本地状态与 API 连接
  columns.ts       # Ant Design Table 列定义
  filters.ts       # Ant Design Form/Input 搜索模型
  components/      # 仅页面内封装
```

- 组件库优先：Ant Design `Table`、`Form`、`Input`、`Select`、`Pagination`、`Button`。
- 关联规则技能：`repo-coding-api`、`repo-coding-components`、`repo-coding-enum`。

## H5 结构示意

这里只是结构示意，不是可直接复制的代码。本仓库不存在 H5 面。

```text
apps/web/src/<mobile-list-module>/
  index.tsx        # 移动端列表入口
  list-item.tsx    # Ant Design Mobile List.Item 占位
```

- 复用与 React 列表相同的数据流，但未经确认不要新增 H5 面。

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
