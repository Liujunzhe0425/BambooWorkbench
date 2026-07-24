# 三模块 v1.1.1 候选重新验收记录（2026-07-24）

验收基线：`origin/integration` `e0affbeef4430dd2691b2ca38d0ccd03b1a07720`。

本轮只验证模块是否遵守仓库流程、公共合同、Runner/TaskService 接入、源码与便携入口边界、
凭据和客户数据边界；模块业务公式、阈值和输出口径仍由各模块负责人负责。

## 结论

三个远端分支均已成功推送并包含最新 `integration`，但当前没有任何一个分支能作为统一
`v1.1.1` 直接合并：水分和售后存在实质性合同/安全前置项，水煮功能兼容验收通过但仍需
把模块版本从 `1.1.0` 更新为经项目负责人确认的 `1.1.1`。因此本轮没有合并模块 PR、没有
修改产品版本、没有合并 `integration -> main`、没有创建标签或 Release。

| 模块 | 最新远端提交 | PR | 同步最新 integration | 修改范围 | 技术复验 | 当前结论 |
|---|---|---|---|---|---|---|
| moisture | `a223cb1` | #52，Draft，目标 `integration` | 是 | 仅 `modules/moisture/` | 522 passed；Ruff/合同/version/self-check 通过 | 退回最小补交 |
| boiling | `ca15d7a` | #54，Draft，目标 `integration` | 是 | 仅 `modules/boiling/` | 48 passed；Ruff/合同/version/self-check 通过；框架 366 passed、8 skipped；真实 smoke 通过 | 功能通过，待版本补交 |
| after_sales | `1ffab60` | 无新 PR | 是 | 仅 `modules/after_sales/` | 50 passed、3 skipped；Ruff/合同/version/self-check 通过 | 退回整改并重新建 PR |

GitHub PR #52、#54 的 `quality` 均在 0 个执行步骤时失败，仍判断为 Actions 调度/账户层
问题，不作为代码失败证据；本地复验结果如上。

## 阻塞项

### 水分

- `supports_incremental` 已正确改为 `true`，历史追加与框架链路测试已补充；
- 但 `capabilities` 仍只有 `ai_report`；
- 公共 `OPERATIONS` 仍只有历史资料与 approved 经验只读四项；
- `run_management.bat manage` 未接入经验三栏写操作、规则三栏操作和当前规则
  `{version, sha256}` 查询；
- 规则 FCR 仍为 `proposed`，经验 FCR 明确写着等待框架复审；
- 模块版本仍为 `1.1.0`。

### 水煮

- 本轮公共合同、TaskService/Runner 兼容性和离线降级均通过；
- 修改仅位于模块目录，无新增 FCR；
- 模块版本仍为 `1.1.0`，与本轮统一 `1.1.1` 目标不一致。

### 售后

- 新分支已推送，但没有创建新的 `module/after-sales -> integration` PR；
- 模块自行使用 `1.6.4`，违反统一版本线；
- 新 FCR 标记 `required_before_module_merge: true`，但框架专属 AI 配置页、凭据接线和启动
  授权尚未实现或获批；
- 模块代码通过 `keyring` 直接读取凭据并直接联网，绕开现有统一 AI Provider 与
  `service_requests` 人工授权合同，同时 `module.json` 仍声明 `requires_network: false`；
- FCR 写入了带人名的客户样表文件名和具体案件信息，违反不得提交客户数据的边界；
- 提交还改变/移除了部分既有输出，业务正确性须由售后负责人自行签字确认。

## 下一次验收范围

三位负责人按各自整改说明更新原分支/PR 后，框架只复验新增提交和受影响接口。三模块全部
合格后，先合入 `integration`，再运行一次组合源码验收并交给项目负责人进行人工测试。
人工测试通过并再次获得明确批准后，才能合并 `integration -> main`；是否打标签、打包和
发布 Release 另行授权。
