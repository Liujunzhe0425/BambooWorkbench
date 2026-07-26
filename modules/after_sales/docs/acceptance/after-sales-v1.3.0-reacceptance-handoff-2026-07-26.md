# 售后模块 v1.3.0 整改复验上下文交接

日期：2026-07-26
PR：[Draft PR #67](https://github.com/Liujunzhe0425/BambooWorkbench/pull/67)
分支：`module/after-sales → integration`
模块版本：`1.3.0`
整改实现提交：`9c91bf58b06f0ef0daa04dc843c8827c7b20c0ea`
框架接入基线：`integration@460a29be73e192d77ae4b8ffcecd4a431ccbc830`

## 1. 本轮复验目的

上一轮售后 v1.3.0 已完成业务月度快照和年度累计内核，但公开边界仍使用 FCR 草案字段，无法通过已经发布的中央 v1.3 月度合同。

本轮不重写售后业务逻辑，只完成中央合同薄适配并重新交付验收，重点解决：

1. manifest 缺少完整 `monthly_rollup` 对象；
2. JobRequest 拒绝任务名称、目标年月和学习开关；
3. finalize 使用多月旁路快照，未返回顶层 `monthly_snapshot`；
4. 投诉类型学习描述只写旁路文件，未进入 `ConfirmationPrompt.learning`；
5. 累计请求和响应仍使用 `request_id / staging_output_dir / errors[]` 等草案字段；
6. 正式 TaskService 链路无法完成月度累计和正式月份提交。

## 2. 交付范围

本轮全部代码和文档修改严格位于 `modules/after_sales/`。

未修改：

- `contracts/`
- `core/`
- `app/`
- `ui/`
- 水分、水煮和 Mock 模块
- `integration`
- `main`
- 中央版本、标签、安装包和 Release

## 3. 已完成整改

### 3.1 Manifest 与 Schema

- `module.json` 已声明完整 `monthly_rollup` 对象；
- 新增 `schemas/confirmation-learning.schema.json`；
- 累计响应 Schema 按中央命名改为 `schemas/monthly-rollup-result.schema.json`；
- 请求、响应、快照和 learning 均由中央合同 CLI 检查真实路径、模块范围和 JSON Schema。

### 3.2 JobRequest 与 finalize

- 接受并校验：
  - `task_name`
  - `period_year`
  - `period_month`
  - `learning_enabled`
- 保持未携带中央年月字段的旧模块调用兼容；
- 中央年月任务 finalize 只为目标年月生成单个内部快照；
- 快照通过 `result.json` 顶层 `monthly_snapshot` 登记；
- 快照不进入普通 `outputs`；
- 目标年月没有已完成人工确认的正式记录时稳定失败，不再静默退回普通成功任务。

### 3.3 公共 learning

- 投诉类型直接返回公共 `ConfirmationPrompt.learning`；
- 字段使用中央 `label` 和 `base_suggestion_id`；
- 上下文层级从品牌＋产品组逐级回退到品牌组；
- 上下文不含客户、姓名、电话、地址、路径、文件名或原始单元格；
- 数值费用和自由文本责任工厂不声明为可学习字段；
- 不再依赖 `after_sales_learning_descriptors.json` 旁路成果。

### 3.4 中央累计请求与响应

累计入口已改用：

- `transaction_id`
- `snapshot_root`
- `output_dir`
- `configuration_identity`
- 中央快照 `snapshot_id / job_id / module_id / year / month / size / sha256`

成功响应确认：

- transaction、模块、版本和目标年月；
- `used_months`；
- snapshot ID、月份和 SHA-256；
- `record_count`；
- 每个成果 SHA-256；
- `network_call_count: 0`。

失败响应使用单个稳定 `error {code,message}`，不输出 traceback、绝对临时路径、环境变量、客户内容或凭据。

## 4. 必须保持的售后边界

- 售后费用、责任工厂和投诉类型继续逐文件人工确认；
- 月度快照及累计成果只使用最终人工值；
- Provider、API Key、本批次授权和审计继续由框架负责；
- 售后模块保持 `requires_network:false`；
- 每个售后任务仍单独询问一次联网授权；
- Provider 只调用一次；
- finalize 和 rollup 不重复联网；
- 品牌、费用、投诉类型、报告、Excel 和图表口径仍由售后模块负责。

## 5. 自动化验证结果

| 检查项 | 结果 |
|---|---|
| 售后模块完整测试（含便携专项） | `61 passed` |
| 中央 MonthlyRunner、MonthlyService、静态合同回归 | `14 passed` |
| 中央合同 CLI | 退出码 `0` |
| Ruff | 通过 |
| Python 编译检查 | 通过 |
| `run_module.bat version` | `after_sales 1.3.0` |
| `run_module.bat self-check` | 通过 |
| 便携运行时构建 | 通过 |
| 便携中央累计入口 | 通过 |
| `git diff --check` | 通过 |

## 6. 已覆盖场景

### 6.1 正常流程

- 单月正式快照；
- 连续多月累计；
- 1 月＋3 月缺月累计；
- 早期月份替换后重新累计；
- 完整累计台账、Word、品牌图、原因图、费用图、年度看板和结构化记录；
- 源码和冻结便携入口使用同一中央请求与响应。

### 6.2 错误与安全

- 非法 JobRequest 年月或学习开关；
- 目标月份没有正式记录；
- 跨年、重复月份、月份乱序和目标月越界；
- snapshot ID、模块、年份、大小和 SHA-256 不一致；
- snapshot root 路径越界；
- 符号链接、junction、重解析点和非普通文件；
- 累计错误稳定返回且不泄露 traceback；
- socket 阻断时累计仍成功，网络调用数为零。

### 6.3 AI 与人工确认

- 未授权时不创建强制 AI 售后任务；
- 已授权后第一次 draft 生成脱敏服务请求；
- Provider 只调用一次；
- 第二次 draft 绑定响应并生成三项必审确认；
- 投诉类型确认携带公共 learning；
- finalize 复用服务响应，服务请求数为零；
- Provider 故障后安全降级并保留输入对账和人工复核。

## 7. 框架验收建议顺序

1. 校验模块合同：

```powershell
.\.venv\Scripts\python.exe -m app.tools.module_contract_cli validate modules\after_sales
```

2. 运行售后完整测试：

```powershell
.\.venv\Scripts\python.exe -m pytest modules\after_sales\tests -q
```

3. 运行中央接入回归：

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\modules\test_monthly_runner.py `
  tests\unit\tasks\test_monthly_service.py `
  tests\contract\test_static_validator.py -q
```

4. 检查：

```powershell
.\.venv\Scripts\python.exe -m ruff check modules\after_sales
modules\after_sales\run_module.bat version
modules\after_sales\run_module.bat self-check
git diff --check
```

5. 使用真实 TaskService 重点观察：
   - draft 服务调用次数为 1；
   - 投诉类型 confirmation 含公共 learning；
   - finalize 顶层含目标年月 `monthly_snapshot`；
   - rollup `network_call_count=0`；
   - 正式月份槽位只在全部成果校验成功后切换。

## 8. 重点复验接口

- `modules/after_sales/module.json`
- `modules/after_sales/schemas/monthly-rollup-request.schema.json`
- `modules/after_sales/schemas/monthly-rollup-result.schema.json`
- `modules/after_sales/schemas/monthly-snapshot.schema.json`
- `modules/after_sales/schemas/confirmation-learning.schema.json`
- `modules/after_sales/src/after_sales_agent/cli.py`
- `modules/after_sales/src/after_sales_agent/manual_review.py`
- `modules/after_sales/src/after_sales_agent/monthly_rollup.py`
- `modules/after_sales/tests/test_task_service_integration.py`
- `modules/after_sales/tests/test_monthly_rollup.py`

## 9. 证据和计划

- 整改计划：
  `modules/after_sales/docs/acceptance/after-sales-v1.3.0-remediation-plan-2026-07-26.md`
- 整改证据：
  `modules/after_sales/docs/evidence/v1.3.0-central-contract-remediation-evidence-2026-07-26.md`
- 原月度累计证据：
  `modules/after_sales/docs/evidence/v1.3.0-monthly-rollup-test-evidence-2026-07-26.md`
- 框架适配请求：
  `modules/after_sales/docs/framework-change-requests/FCR-after_sales-20260726-monthly-rollup-integration.md`

## 10. 已知限制

1. 图片和 PDF 仍不是售后模块正式输入。
2. 无有效报修年月的记录不会被猜测为目标月份，也不能进入正式月度快照。
3. 当前模块版本保持 `1.3.0`；中央正式发布版本、标签、安装包和 Release 仍由框架负责人统一决定。

本轮没有已知的售后中央合同阻断项。

## 11. 回滚

如本轮薄适配需要整体回滚：

```text
git revert 9c91bf58b06f0ef0daa04dc843c8827c7b20c0ea
```

该操作只撤销售后模块整改，不需要回滚中央框架合同；此前 v1.2.1 Excel 兼容修复和 v1.2.0 框架托管 AI 基线不受影响。
