# 框架事项状态总览

> 文档职责：只维护事项状态、责任方和下一步，不重复保存实施规格。
>
> 最后核对：2026-07-23；当前模块版本：`0.1.2`。

三功能页面、轻量历史资料、AI报告和规则管理的框架需求，以
[`framework-change-requests/FCR-moisture-20260723-three-function-workbench.md`](framework-change-requests/FCR-moisture-20260723-three-function-workbench.md)
为唯一权威规格。下一阶段简化业务架构以
[`architecture/moisture-next-stage-architecture.md`](architecture/moisture-next-stage-architecture.md)
为准。本文件不复制两者的字段、流程、Schema 或验收矩阵。

## 当前状态

| 事项 | 状态 | 责任方 | 下一步/权威依据 |
| --- | --- | --- | --- |
| 正式 moisture 注册与独立进程调用 | 已完成模块与源码验收 | 框架方 | 默认使用正式模块；继续纳入发布回归，不再作为开放缺陷 |
| DeepSeek / OpenAI-compatible Provider 基础接入 | 已实现，待真实环境验收 | 框架方、安全负责人 | 使用 Windows 凭据、联网开关和逐次同意完成生产环境联调；Provider 异常仍需结构化降级 |
| 三功能首页与操作编排 | 待框架审核 | 框架方、模块方 | 见新FCR；入口为汇总表生产、AI辅助分析和规则库管理 |
| 历史追加与轻量历史资料 | 待模块实现、框架适配 | 模块方、框架方 | 标准表直接导入；企业旧表必须受控映射和预览确认；不建设数据库 |
| 经验库治理 UI | 待框架审核 | 框架方、模块方 | 复用模块现有draft/approved/retired生命周期，由新FCR统一请求管理入口 |
| 独立 AI 报告与候选规则 | 待模块实现、框架适配 | 框架方、模块方、业务负责人 | 报告不修改XLSX；候选规则只能进入草稿，不能自动发布 |
| 轻量规则管理与任务快照 | 待框架审核 | 框架方、模块方 | 仅草稿、当前规则、历史版本三栏；单人确认、原子发布和恢复 |
| `0.55/0.47` 均值阈值业务批准 | 待业务批准 | 业务负责人 | 当前 `default-v2-approved` 机器资产仍标记 confirmed；业务批准完成前继续按“待批准筛查提示”说明 |
| 便携包正式发布签署 | 待发布阶段完成 | 发布负责人 | 源码、合同、BAT 和模块测试已通过；正式交付时重新构建并完成便携环境签署 |

## 已关闭事项

- 主框架默认 `use_mocks=False`，正式 `modules/moisture` 可由 Registry 发现；
- Runner 通过 `run_module.bat` 启动独立模块进程，不需要框架 import moisture 业务实现；
- 模块合同、`version`、`self-check`、历史样本和源码调用链已完成验收；
- 框架 Bootstrap 已能组合 DeepSeek、OpenAI-compatible、Mock 和不可用 Provider；
- 模块继续只声明 service request、校验 service response，不持有 HTTP 客户端或 API Key。
- 旧“冻结数据集、复杂治理工作器、全量回放和人工复核中心”方案已归档，不再作为下一阶段实施依据。

## 维护规则

1. 这里只更新状态、责任方和链接；不得复制 FCR 的详细协议或验收条款。
2. 已完成事项移入“已关闭事项”，不继续描述为待开发能力。
3. FCR 获批、拒绝或拆分后，只同步状态和新文档链接。
4. 业务阈值批准必须引用正式批准记录，不能仅凭机器包中的 `confirmed` 字段关闭。
