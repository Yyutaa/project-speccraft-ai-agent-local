---
name: repo-coding-permission
description: 查找并应用本仓库的权限点、功能开关和访问控制规则。
---

# 仓库编码：权限

## 用途

确认是否存在前端权限模型，并保持服务端强制校验的权威性。

## 上下文读取

- 读取 `AGENTS.md` 了解 Repo Guide 入口信息。
- 读取 `repo-profile.md` 中相关的稳定事实、修改边界、命令、共享包范围、应用运行时拓扑和应用到包依赖映射章节。
- 只在需要证据时检查当前仓库源码。

## 证据入口

- 轻量采样中未找到证据
- 未发现权限辅助函数、功能开关或受保护 UI 组件。后端的只读仓库权限不是前端访问控制层。
- 这些采样路径只是证据入口，不是全局强制实现规则。当同应用、同框架、同模块的当前示例与这些入口不一致时，优先使用当前示例。
- 除非用户明确确认这些路径为稳定的仓库级约束，否则只把它们当作查找锚点，而不是强制全局规则。

## 按框架查找

- React：无证据；只有明确要求加守卫时，才检查 `apps/web/src/api.ts` 和目标 UI。
- Vue：轻量采样中未找到证据
- H5：轻量采样中未找到证据

## 需要检查的内容

- 作为现有服务端驱动操作门禁的 `Run.available_commands`
- 任何可能被误当作授权的 UI 入口

## 需要避免的内容

- 实现仅客户端授权
- 把隐藏按钮当作安全边界

## 需要确认

- 权限模型和强制校验点
- 后端是否已拒绝该操作

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
- 服务端校验是权威；前端只能反映它。
