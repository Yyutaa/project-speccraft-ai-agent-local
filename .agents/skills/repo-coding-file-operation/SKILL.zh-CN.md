---
name: repo-coding-file-operation
description: 查找并应用本仓库的上传、下载、导入、导出和 blob 处理规则。
---

# 仓库编码：文件操作

## 用途

在新增上传、下载或导出行为之前，先找到真实的文件流边界。

## 上下文读取

- 读取 `AGENTS.md` 了解 Repo Guide 入口信息。
- 读取 `repo-profile.md` 中相关的稳定事实、修改边界、命令、共享包范围、应用运行时拓扑和应用到包依赖映射章节。
- 只在需要证据时检查当前仓库源码。

## 证据入口

- 轻量采样中未找到证据
- 未发现上传/下载辅助函数或 blob 处理。需求文件访问是服务端路径字段，不是浏览器上传。
- 这些采样路径只是证据入口，不是全局强制实现规则。当同应用、同框架、同模块的当前示例与这些入口不一致时，优先使用当前示例。
- 除非用户明确确认这些路径为稳定的仓库级约束，否则只把它们当作查找锚点，而不是强制全局规则。

## 按框架查找

- React：无证据；如果涉及文件字段，检查 `api.ts` 的请求类型。
- Vue：轻量采样中未找到证据
- H5：轻量采样中未找到证据

## 需要检查的内容

- `apps/web/src/api.ts` 中任何文件相关请求字段
- `apps/web/src/App.tsx` 的路径输入处理

## 需要避免的内容

- 契约要求服务端相对路径时，改为实现浏览器文件上传
- 从浏览器读取本地绝对路径

## 需要确认

- 流程是上传还是服务端路径选择
- 后端契约允许的文件类型和大小限制

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
- 文件路径安全由后端强制；前端不得假装授权路径。
