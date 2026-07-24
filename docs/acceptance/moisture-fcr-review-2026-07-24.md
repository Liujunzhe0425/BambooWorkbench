# 水分模块 PR #52 框架适配请求审核记录

审核对象：`module/moisture-test`，提交 `0fc2d48`，PR #52。

## 审核结论

三个需求的业务方向与既定责任边界一致，但当前交付成熟度不同：

| 请求 | 合理性 | 当前模块交付 | 框架处理 |
|---|---|---|---|
| 历史标准汇总追加新原始数据 | 合理 | 模块内核、配置解析、去重/冲突/重算测试已完成 | 已实现受能力声明控制的入口和任务配置 |
| 经验草稿/已批准/历史三栏管理 | 合理 | 只有模块内部 service/repository，未进入公开管理合同 | 暂不显示入口，等待模块补交公开合同 |
| 规则三栏管理及任务规则快照 | 合理，但发布标准仍需业务批准 | 只有模块内部 service/repository，未进入公开管理合同 | 暂不显示入口，等待模块补交公开合同和业务批准 |

模块完整回归结果为 `493 passed`，Ruff、模块合同和真实模式烟雾检查通过。
GitHub `quality` 检查在没有任何执行步骤的情况下失败，属于 Actions 调度/账户层失败，
不能替代本地代码验收结果。

## 框架已完成的历史追加适配

- 水分任务页面支持“创建新的水分汇总表 / 在历史标准汇总表上追加”两种方式；
- 追加方式分别选择一份历史基表和一份或多份新原始 Excel；
- 框架只生成 `operation=append_summary` 和精确的输入角色，不解析 Excel 或实现业务合并；
- 输入仍由 TaskService 建立只读快照，draft/finalize 继续复用原确认流程；
- 只有模块清单声明 `supports_incremental: true` 时才显示入口，避免旧模块误调用。

## 水分负责人需要最小补交的内容

当前 `modules/moisture/module.json` 仍声明 `supports_incremental: false`，因此框架会按安全设计
隐藏历史追加入口。水分负责人应在确认正式支持后改为 `true`，并补充从
Registry → TaskService → Runner → `run_module.bat` 的合同测试。

经验和规则管理不能直接由框架导入模块 Python 内部类。水分负责人还需：

1. 在模块清单 `capabilities` 中声明稳定能力名，例如
   `experience_management`、`rule_management`、`rule_snapshot`；
2. 扩展模块私有的 `module-management-request.schema.json`、
   `module-management-response.schema.json` 和 `OPERATIONS`；
3. 将创建、更新、校验、预览、发布、停用、恢复和历史复制操作接入
   `run_management.bat manage`；
4. 对所有请求字段、公开响应、哈希冲突、路径越界和错误降级补充合同测试；
5. 提供一个只读操作返回当前有效规则的 `{version, sha256}`，供框架在创建任务时固化；
6. 保证正式 `run_module.bat` 仍不暴露可写管理接口。

完成后更新原 PR #52，不要直接修改 `integration` 或 `main`。框架再次验收公开合同后，
再实现经验/规则三栏页面和规则快照接线。

## 暂不允许宣称的能力

- 当前客户界面尚未提供经验和规则三栏管理；
- 当前框架尚不能通过公开进程合同读取规则身份并固定快照；
- 在品质负责人确认单人发布权限、scope 定义和正式阈值前，不得把测试值描述为生产标准，
  也不得允许 AI 自动发布规则。
