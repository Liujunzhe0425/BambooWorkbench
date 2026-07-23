# 框架事项状态总览

> 文档职责：只维护事项状态、责任方和下一步，不重复保存实施规格。
>
> 最后核对：2026-07-23；当前模块版本：`1.0.1`。

v1.0.1独立AI报告、approved经验选择和轻量历史资料选择的框架需求，以
[`framework-change-requests/FCR-moisture-20260723-ai-report-context-selection.md`](framework-change-requests/FCR-moisture-20260723-ai-report-context-selection.md)
为当前唯一有效FCR。下一阶段总体业务架构以
[`architecture/moisture-next-stage-architecture.md`](architecture/moisture-next-stage-architecture.md)
为准；v1.0.1模块实施边界见
[`architecture/moisture-v1.0.1-independent-ai-report-plan.md`](architecture/moisture-v1.0.1-independent-ai-report-plan.md)。本文件不复制其字段、流程、Schema或验收矩阵。

## 当前状态

| 事项 | 状态 | 责任方 | 下一步/权威依据 |
| --- | --- | --- | --- |
| 正式 moisture 注册与独立进程调用 | 已完成模块与源码验收 | 框架方 | 默认使用正式模块；继续纳入发布回归，不再作为开放缺陷 |
| DeepSeek / OpenAI-compatible Provider 基础接入 | 已实现，待真实环境验收 | 框架方、安全负责人 | 使用 Windows 凭据、联网开关和逐次同意完成生产环境联调；Provider 异常仍需结构化降级 |
| 历史追加、候选规则和规则管理 | 延期 | 模块方、框架方 | 不进入v1.0.1当前FCR，后续分别提交独立请求 |
| `0.55/0.47` 均值阈值业务批准 | 待业务批准 | 业务负责人 | 当前 `default-v2-approved` 机器资产仍标记 confirmed；业务批准完成前继续按“待批准筛查提示”说明 |
| GitHub Actions `quality` | 外部阻塞 | 仓库负责人 | job 未获 Runner、无测试步骤；按 GitHub 注释处理账户付款或 Actions spending limit 后重跑 |
| 便携包正式发布签署 | 待发布阶段完成 | 发布负责人 | 完整便携构建、portable verification 和冻结 EXE 闭环已通过；正式发布仍需签名与发布批准 |

## 已关闭事项

- 主框架默认 `use_mocks=False`，正式 `modules/moisture` 可由 Registry 发现；
- Runner 通过 `run_module.bat` 启动独立模块进程，不需要框架 import moisture 业务实现；
- 模块合同、`version`、`self-check`、历史样本和源码调用链已完成验收；
- 框架 Bootstrap 已能组合 DeepSeek、OpenAI-compatible、Mock 和不可用 Provider；
- 模块继续只声明 service request、校验 service response，不持有 HTTP 客户端或 API Key。
- 框架 PR #43 已提供独立 AI 报告入口、受控模块数据目录、管理进程宿主、历史/approved 经验选择和 Provider 编排；
- v1.0.1 模块已提供四表汇总、独立 AI 报告、历史资料管理入口和 approved 经验目录；
- 本地最终门禁为模块 418 passed，冻结 EXE 主框架闭环 5 passed；CI 红叉为 GitHub Billing 阻塞，不是代码失败；
- 旧“冻结数据集、复杂治理工作器、全量回放和人工复核中心”方案已归档，不再作为下一阶段实施依据。
- 旧“三功能工作台一次性交付”FCR已归档；框架适配改为按独立AI报告、历史追加、规则治理分阶段申请。

## 维护规则

1. 这里只更新状态、责任方和链接；不得复制 FCR 的详细协议或验收条款。
2. 已完成事项移入“已关闭事项”，不继续描述为待开发能力。
3. FCR 获批、拒绝或拆分后，只同步状态和新文档链接。
4. 业务阈值批准必须引用正式批准记录，不能仅凭机器包中的 `confirmed` 字段关闭。
