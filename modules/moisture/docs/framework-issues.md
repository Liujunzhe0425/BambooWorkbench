# 框架事项状态总览

> 文档职责：只维护事项状态、责任方和下一步，不重复保存实施规格。
>
> 最后核对：2026-07-22；当前模块版本：`0.1.2`。

规则治理、任务规则快照和人工复核的完整需求，以
[`framework-change-requests/FCR-moisture-20260721-rule-governance-runtime-analysis.md`](framework-change-requests/FCR-moisture-20260721-rule-governance-runtime-analysis.md)
为唯一权威规格。下一阶段业务架构以
[`architecture/moisture-next-stage-architecture.md`](architecture/moisture-next-stage-architecture.md)
为准。本文件不复制两者的字段、流程、Schema 或验收矩阵。

## 当前状态

| 事项 | 状态 | 责任方 | 下一步/权威依据 |
| --- | --- | --- | --- |
| 正式 moisture 注册与独立进程调用 | 已完成模块与源码验收 | 框架方 | 默认使用正式模块；继续纳入发布回归，不再作为开放缺陷 |
| DeepSeek / OpenAI-compatible Provider 基础接入 | 已实现，待真实环境验收 | 框架方、安全负责人 | 使用 Windows 凭据、联网开关和逐次同意完成生产环境联调；Provider 异常仍需结构化降级 |
| 规则治理、active binding、任务规则快照与人工复核 | 待框架审核 | 框架方、模块方 | 见上述 FCR；本文件不重复其实现要求 |
| 经验库治理 UI | 待立项 | 框架方、模块方 | 复用模块现有离线治理生命周期；如需框架改动，应另建独立 FCR |
| AI 报告增强 | 待设计与验收 | 框架方、模块方、业务负责人 | AI 只能增强确定性报告，不重算数值或形成责任/不合格结论 |
| `0.55/0.47` 均值阈值业务批准 | 待业务批准 | 业务负责人 | 当前 `default-v2-approved` 机器资产仍标记 confirmed；业务批准完成前继续按“待批准筛查提示”说明 |
| 便携包正式发布签署 | 待发布阶段完成 | 发布负责人 | 源码、合同、BAT 和模块测试已通过；正式交付时重新构建并完成便携环境签署 |

## 已关闭事项

- 主框架默认 `use_mocks=False`，正式 `modules/moisture` 可由 Registry 发现；
- Runner 通过 `run_module.bat` 启动独立模块进程，不需要框架 import moisture 业务实现；
- 模块合同、`version`、`self-check`、历史样本和源码调用链已完成验收；
- 框架 Bootstrap 已能组合 DeepSeek、OpenAI-compatible、Mock 和不可用 Provider；
- 模块继续只声明 service request、校验 service response，不持有 HTTP 客户端或 API Key。

## 维护规则

1. 这里只更新状态、责任方和链接；不得复制 FCR 的详细协议或验收条款。
2. 已完成事项移入“已关闭事项”，不继续描述为待开发能力。
3. FCR 获批、拒绝或拆分后，只同步状态和新文档链接。
4. 业务阈值批准必须引用正式批准记录，不能仅凭机器包中的 `confirmed` 字段关闭。
