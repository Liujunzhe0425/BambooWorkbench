# 售后分析模块 v1.1.1 框架 AI 适配验收

日期：2026-07-25
分支：`module/after-sales`
目标：`module/after-sales -> integration` Draft PR #57
框架基线：`integration@a7b66f95ec3fa535501c43bc1f4548135a5baa45`

## 完成范围

- 模块版本保持 `1.1.1`。
- `requires_network` 保持 `false`。
- 增加 `framework_ai.required=true`、`setup_page=module`、`service_before_confirmation=true`。
- 接通第一次 draft、框架服务、第二次 draft、人工确认和 finalize。
- 删除模块本地凭据读取、Provider HTTP 网关、直连开关和相关依赖。
- AI 失败或不可用时保留全部输入、离线分析、人工复核和完整输出。

## 合同证据

| 阶段 | 服务请求 | 业务确认 | 行为 |
|---|---:|---:|---|
| 第一次 draft | 每个成功案件恰好进入一个请求批次 | 0 | 解析并生成脱敏请求 |
| 第二次 draft | 0 | 每个成功案件至少 3 项必审 | 校验并绑定 AI 候选 |
| finalize | 0 | 已回答项为 0 | 复用响应并应用人工值 |

真实 `TaskService` 测试使用内存 Provider 和实际模块进程，确认 Provider 总调用次数在第二次 draft 后为 1，finalize 后仍为 1；重复 finalize 抛出 `InvalidTaskTransition`。未授予强制 AI 权限时，框架在创建任务前拒绝，任务目录和 Provider 调用均不产生。

## 降级与输入保留

- 成功：AI 品牌、原因、分类和责任工厂候选可绑定，受控字段继续人工确认。
- 部分失败：成功批次正常绑定，超时批次保留离线值并进入复核。
- 拒绝或服务错误：所有成功解析记录标记 AI 降级，不删除、不跳过。
- 非法响应：拒绝整个不完整或非法批次，不接受部分案件结果。
- 文件损坏：保留失败对账行，其他文件继续请求、复核和导出。

## 安全证据

- 模块源码不导入凭据库、`urllib.request` 或 `httpx`。
- 模块依赖不包含凭据库客户端。
- 自检、单元测试、源码入口和便携入口不读取真实 API Key。
- 对外请求删除身份字段、原文件名和本机路径，并限制单批大小。
- 任务响应只保存框架返回的业务 JSON；不保存 API Key。
- finalize 不生成 `service_requests`，模块进程不具备联网实现。

## 输出

本次适配未新增、删除或改名业务输出：

- `after_sales_master_summary.xlsx`
- `after_sales_records.json`
- `after_sales_analysis_report.docx`
- `after_sales_brand_share.xlsx`
- `after_sales_reason_share.xlsx`
- `after_sales_monthly_fee.xlsx`
- `after_sales_yearly_dashboard.xlsx`
- `result.json`

业务自测使用完全虚构的脱敏样例，确认人工费用、责任工厂和投诉类型在 JSON、汇总表、图表和报告中使用同一最终口径。输出集合和既有 1.1.1 业务实现保持一致，需售后负责人确认业务正确性。

## 验证命令

```powershell
python -m pytest modules/after_sales/tests -q
python -m ruff check modules/after_sales
python -m app.tools.module_contract_cli validate modules/after_sales
modules\after_sales\run_module.bat version
modules\after_sales\run_module.bat self-check
git diff --check
```

本次模块测试结果为 `39 passed`；Ruff、模块合同、源码 version/self-check、冻结 EXE 协议、
便携 draft/finalize 闭环和 `git diff --check` 均通过。最终提交 SHA 在 PR #57 更新中记录。

## 框架重点复验

1. 售后 AI 配置页门禁与本批次授权是否在创建任务前生效。
2. `service-response.json` 在重启恢复、Provider 部分失败和异常终止时的任务本地完整性。
3. 第二次 draft 的确认提示在 UI 中是否逐文件展示且不可批量误用。
4. finalize 是否始终复用响应，Provider 调用次数保持不变。
5. 便携版是否使用框架 Provider，并保持模块 EXE 无凭据和网络能力。
