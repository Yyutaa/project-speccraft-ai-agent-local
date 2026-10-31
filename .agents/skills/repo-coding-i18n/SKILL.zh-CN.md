---
name: repo-coding-i18n
description: 查找并应用本仓库的翻译键、语言资源和文本渲染规则。
---

# 仓库编码：国际化

## 用途

在修改或抽取用户可见文本之前，先确认是否存在本地化体系。

## 上下文读取

- 读取 `AGENTS.md` 了解 Repo Guide 入口信息。
- 读取 `repo-profile.md` 中相关的稳定事实、修改边界、命令、共享包范围、应用运行时拓扑和应用到包依赖映射章节。
- 只在需要证据时检查当前仓库源码。

## 证据入口

- 轻量采样中未找到证据
- 当前 UI 文案是 `apps/web/src/App.tsx` 和治理组件中的内联中文；未发现 locale 文件或翻译封装。
- 这些采样路径只是证据入口，不是全局强制实现规则。当同应用、同框架、同模块的当前示例与这些入口不一致时，优先使用当前示例。
- 除非用户明确确认这些路径为稳定的仓库级约束，否则只把它们当作查找锚点，而不是强制全局规则。

## 按框架查找

- React：无证据；只有明确要求改文案时，才检查目标组件中的内联文案。
- Vue：轻量采样中未找到证据
- H5：轻量采样中未找到证据

## 需要检查的内容

- 当请求只涉及文案时，检查目标组件的内联文本
- 如果提议新增 i18n 依赖，检查 `apps/web/package.json`

## 需要避免的内容

- 臆造 locale 目录或翻译键
- 在无关改动中混入新的 i18n 体系

## 需要确认

- 仓库是否应引入 i18n
- 现有内联中文是否是有意为之的产品选择

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
- 仓库没有 i18n 框架时，不要把它当作默认方案。
