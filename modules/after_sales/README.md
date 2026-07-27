# 售后统计模块（1.3.1）

`after_sales` 是 BambooWorkbench 的售后 Excel 分析模块。模块解析每份输入，生成品牌、月份、问题原因、三类金额、处理状态、图表和 Word 报告，并要求逐文件人工确认售后费用、责任工厂和投诉类型。

标准工作流强制使用框架托管 AI。模块只生成脱敏 `service_requests` 并消费任务目录中的 `service-response.json`；API Key、Provider HTTP 调用、授权和审计均由主框架负责。模块进程自身不读取凭据、不联网，因此 `module.json` 保持 `requires_network: false`。

## 运行环境

- Windows 10/11
- Python 3.10 或更高版本
- 依赖见 `requirements.txt`

```bat
pip install -r requirements.txt
run_module.bat version
run_module.bat self-check
run_module.bat run --job D:\data\job.json
```

便携版由仓库根目录执行下列命令安装模块冻结运行时：

```powershell
powershell -ExecutionPolicy Bypass -File modules/after_sales/build_portable_runtime.ps1
```

## 框架 AI 合同

模块清单声明：

```json
{
  "requires_network": false,
  "framework_ai": {
    "required": true,
    "setup_page": "module",
    "service_before_confirmation": true
  }
}
```

任务顺序固定为：

1. 用户在框架售后 AI 接入页完成 Provider、模型、连接测试和本批次授权。
2. 第一次 `draft` 解析所有 Excel，为每个成功案件生成限长、脱敏的 AI 请求，不生成业务确认。
3. 框架 Provider 执行请求并写入任务本地 `protocol/service-response.json`。
4. 框架使用同一 `job_id` 和 `service_response_file` 运行第二次 `draft`。
5. 模块校验并绑定 AI 建议，然后生成逐文件“售后费用、责任工厂、投诉类型”三项阻断确认。
6. `finalize` 复用同一响应文件并应用人工答案，不再生成 AI 请求。

## 任务年月冲突

当中央任务提供目标年月时，模块会在 Excel 解析完成、生成框架 AI 请求之前，对目标年月与“提出质量问题/报修日期”进行脱敏比对：

- 全部记录属于目标年月：继续正常 AI 和人工复核流程。
- 同时存在目标月、其他年月或年份未注明记录：在第二次 draft 显示阻断式“任务年月范围”确认；正式月度快照只写入目标年月记录，其他记录的原业务日期保持不变。
- 目标月确定匹配为 0 且所有记录年月均明确：draft 立即以 `TASK_PERIOD_ZERO_MATCH` 停止，不创建 AI 请求、普通业务确认、正式快照或成果文件。
- 年份或月份未注明：要求人工补全“提出质量问题/报修日期”；模块不会按任务年月猜测或静默改写日期。

冲突说明只给出目标年月、已知年月分布、目标匹配数和年月未注明数量，不包含客户名称、Excel 原文或本机绝对路径。工作台如需提供“返回修改年月”或“取消任务”的专用按钮，见独立 FCR。

AI 可提供品牌、问题类型、原因、费用、责任工厂、方案和处理状态候选。费用、责任工厂、责任认定、赔偿及结案状态不能由 AI 绕过确定性证据和人工确认写成最终结论。

Provider 超时、拒绝、错误、响应缺失或 JSON 非法时，模块保留每份输入的离线结果和失败对账，继续人工复核及完整导出。用户在任务开始前拒绝强制 AI 授权时，由框架阻止创建任务。

## 月度快照与年度累计

模块清单声明完整的中央 `monthly_rollup` 合同。finalize 成功且目标年月内的正式记录均已完成“售后费用、责任工厂、投诉类型”三项人工确认时，模块在输出目录生成单个内部快照：

- `after_sales_monthly_snapshot.json`：只包含中央 JobRequest 指定目标年月的标准内部快照。

快照通过 `result.json` 顶层 `monthly_snapshot` 登记，不作为普通用户成果展示；它不保存客户原文、客户身份、绝对输入路径或原始单元格，只保留年度累计所需的脱敏结构化最终值。

框架可使用模块自有合同调用完全离线的累计入口：

```bat
run_module.bat rollup --request D:\data\rollup-request.json --response D:\data\rollup-response.json
```

请求使用中央 `transaction_id / snapshot_root / output_dir / configuration_identity` 合同，并提供同模块、同年份、严格按月份升序且不大于目标月的正式快照身份、任务身份、大小及 SHA-256。允许月份缺口；重复月、乱序、跨年、越界、大小或哈希损坏、路径越界、符号链接或 junction 会返回稳定错误码。

累计入口不导入 AI 服务适配代码，不读取 API Key、Windows 凭据或 Provider，不发送服务请求。它只复用快照中的最终人工值，生成截至目标月份的累计台账、Word 报告、品牌/原因/费用图表、年度看板和结构化业务记录。

模块自有 Schema 位于：

- `schemas/monthly-snapshot.schema.json`
- `schemas/monthly-rollup-request.schema.json`
- `schemas/monthly-rollup-result.schema.json`
- `schemas/confirmation-learning.schema.json`

投诉类型确认项直接通过公共 `ConfirmationPrompt.learning` 提供稳定、脱敏的候选和上下文；费用及自由文本责任工厂不声明为可学习字段。框架已提供正式月份槽位、替换事务、后续月份重算、公共学习合同和历史数据页面，模块通过中央 Runner 参与原子累计事务。

## 数据边界

- 请求不包含客户、联系人、销售、电话、邮箱、地址、订单号、本机路径、原文件名或 Excel 二进制。
- 请求按稳定案件 ID 分批，并设置 `response_format: json_object`。
- 响应必须匹配任务、模块、请求和案件 ID；缺失、重复、越界或非法字段均按对应批次降级。
- API Key 不进入任务、SQLite、输出、日志、异常、模块配置、安装包或 Git。
- 模块不会修改、删除或重命名任何输入文件。

## 输出

- `after_sales_master_summary.xlsx`：全量售后台账及复核状态。
- `after_sales_records.json`：逐输入结构化明细和分析来源。
- `after_sales_analysis_report.docx`：与结构化记录使用同一数据源的分析报告。
- `after_sales_brand_share.xlsx`：品牌案件数量与占比图表。
- `after_sales_reason_share.xlsx`：问题原因数量与占比图表。
- `after_sales_monthly_fee.xlsx`：年度月度费用和案件数量图表。
- `after_sales_yearly_dashboard.xlsx`：按年份汇总的品牌、原因和月份图表。
- `result.json`：BambooWorkbench 模块运行合同结果。

## 业务规则

- 品牌与客户字段严格分离；无明确证据时品牌为 `未知`。
- 问题类型为 `性能`、`外观`、`加工`、`其他`，一个案件可保留多个候选，人工确认最终主类型。
- 企业售后成本、内部责任扣款和外部承担金额分别提取和统计，未知金额保持空值。
- 重复文件仍逐份保留；损坏文件写入稳定错误码，不影响其他文件。
- 日期只使用质量问题、报修或投诉日期，不用订单、交货、文件名或文件时间补齐。
- 所有正式输出以人工复核值为最终口径。
- 投诉类型确认项提供稳定、脱敏的学习描述；非枚举费用和自由文本责任工厂不由框架自行推断学习场景。

业务关键词和字段同义词位于 `rules/default_rules.yaml`。

## 验证

测试只使用仓库内完全虚构的脱敏样例，默认不读取凭据、不发起网络请求：

```powershell
python -m pytest modules/after_sales/tests -q
python -m ruff check modules/after_sales
python -m app.tools.module_contract_cli validate modules/after_sales
modules\after_sales\run_module.bat version
modules\after_sales\run_module.bat self-check
git diff --check
```
