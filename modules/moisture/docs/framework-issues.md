# 框架事项状态总览

> 文档职责：只维护事项状态、责任方和下一步，不重复保存实施规格。
>
> 最后核对：2026-07-24；当前模块版本：`1.1.1`。

## 当前状态

| 事项 | 状态 | 责任方 | 下一步/权威依据 |
| --- | --- | --- | --- |
| 正式 moisture 注册、任务进程与历史追加 | 已完成模块实现 | 框架方 | 保持 `supports_incremental=true`，复验 Registry → TaskService → Runner → BAT |
| 统一 v1.1 管理进程合同 | 模块已实现，待框架复验 | 框架方 | [`FCR-moisture-20260724-public-management-contract.md`](framework-change-requests/FCR-moisture-20260724-public-management-contract.md) |
| 经验管理三栏 | 模块 10 个公开操作已接入 BAT，GUI 待适配 | 框架方 | 通过中央 ManagementService/Runner 调用，不得直接 import 模块内部服务 |
| 规则管理三栏 | 模块 12 个治理操作已接入 BAT，GUI 待适配 | 框架方 | 复验草稿、预览、发布、停用、恢复和历史复制 |
| 当前规则身份与任务快照 | 模块查询和固定快照已实现，自动注入待适配 | 框架方 | TaskService 创建任务时查询并固定 `{version, sha256}`，draft/finalize 使用同一身份 |
| 管理合同发现 | 中央 manifest 尚不支持模块自有 Schema 描述 | 框架方 | 按统一 FCR 增加安全的相对 Schema 路径发现及请求/响应前后置校验 |
| DeepSeek / OpenAI-compatible Provider | 已有框架能力，待生产环境验收 | 框架方、安全负责人 | 使用 Windows 凭据、联网开关和逐次同意；异常结构化降级 |
| `0.55/0.47` 均值阈值业务批准 | 待业务批准 | 业务负责人 | 继续标注为待批准筛查提示，不得称为正式生产标准 |
| 便携包正式发布签署 | 待发布阶段 | 发布负责人 | 复验 v1.1.1 管理入口后执行签名、发布与回滚准备 |

## 模块已交付边界

- 正式任务入口继续为 `run_module.bat`，管理入口为 `run_management.bat manage`；
- 模块 v1.1.1 的管理合同覆盖 27 个操作：旧历史四操作、经验十操作、规则十二操作和当前规则身份查询；
- v1.0 四操作保持兼容；v1.1 请求/响应由模块 Schema 严格校验；
- 正式 draft/finalize 依赖图不能触达可写经验或规则管理端；
- 规则发布生成不可变版本和 SHA-256；已有 draft/finalize 使用固定规则快照；
- AI 不得自动发布规则，模块不持有 HTTP Provider、API Key 或网络职责；
- 模块测试结果和提交号以 Draft PR #52 最新证据为准，不沿用旧版本固定测试数量。

## 框架不得绕过的边界

1. 不得因中央 v1.0 管理合同不足而直接 import 模块 repository/service。
2. 不得在未校验模块请求和响应 Schema 时向 GUI 宣称新管理能力可用。
3. 正式任务失败时不得静默回退 moisture Mock。
4. TaskService 必须在任务创建时固定规则身份；finalize 不得重新选择当前 active。
5. 业务阈值、规则含义和经验内容仍由业务负责人批准，框架不接管业务判断。

## 维护规则

1. 本文件只更新状态、责任方和链接，不复制 FCR 的详细协议。
2. FCR 批准、拒绝或拆分后，只同步状态和新文档链接。
3. 业务阈值批准必须引用正式批准记录，不能仅凭规则包字段关闭。
