# 售后统计模块（1.1.0）

本模块是售后 Excel 智能汇总网站的业务处理核心，已整理为 BambooWorkbench 的 `after_sales` 模块包。它从售后申请 Excel 中抽取客户、地点、销售、产品、订单、报修日期、反馈、调查、方案、三类金额和处理状态，并按参考模板生成品牌/月度汇总、逐年售后明细、图表与分析报告。1.1.0 使用竹简工作台统一 `service_requests` AI 授权协议和逐文件人工复核，并提供排版后的 Word 报告及年度图表总览。

本目录只包含处理引擎、规则、模板、脱敏样本、测试和交接文档；不包含独立网页、运行日志、客户原表、API Key 或用户产物中的本机绝对路径。2026-07-18 整改在保留既有解析能力的基础上，补齐了离线无冗余确认、三类金额、多标签汇总、图表、分析报告、路径脱敏和损坏文件中文错误。

## 运行环境

- Windows 10/11
- Python 3.10 或更高版本
- 依赖见 `requirements.txt`
- 离线规则模式不需要网络，也不会因为未配置 AI 而阻断结果生成

安装依赖：

```bat
pip install -r requirements.txt
```

## 命令

```bat
run_module.bat version
run_module.bat self-check
run_module.bat run --job D:\data\job.json
```

如果 Python 没有加入 PATH，可以指定：

```bat
set PYTHON_EXE=C:\path\to\python.exe
run_module.bat self-check
```

Windows 便携包会在模块目录的 `runtime` 中携带独立运行时；`run_module.bat`
会优先使用该运行时，不依赖使用者电脑上的 Python 或第三方库。框架便携版构建完成后，
在仓库根目录执行以下命令把售后运行时装入便携目录：

```powershell
powershell -ExecutionPolicy Bypass -File modules/after_sales/build_portable_runtime.ps1
```

进度协议使用 ASCII 安全的 JSON 转义输出。这样即使 Windows 冻结程序所在控制台仍为
GBK，工作台也能按严格 UTF-8 逐行读取，JSON 解码后中文消息保持不变。构建脚本会运行
冻结程序协议验收，非 UTF-8 或非逐行 JSON 的便携运行时不会通过打包。

## 统一任务合同

```json
{
  "schema_version": "1.0",
  "job_id": "sample-after-sales",
  "module_id": "after_sales",
  "phase": "draft",
  "run_mode": "batch",
  "input_files": [
    "D:/BambooWorkbench/tasks/sample/input/sample_after_sales.xlsx"
  ],
  "output_dir": "D:/BambooWorkbench/tasks/sample/output",
  "module_config_file": null,
  "ai_enabled": false,
  "allowed_knowledge_scopes": [],
  "parent_job_id": null,
  "confirmation_file": null,
  "service_response_file": null
}
```

框架会在 `input_files` 中传入只读 Excel 副本的绝对路径。模块不会修改、删除或重命名输入文件，只向 `output_dir` 写入结果。每个成功解析的案件在 `draft` 后固定进入人工复核，必须逐条核对“售后费用、责任工厂、投诉类型”；`finalize` 阶段读取 `confirmation_file`，把确认值写入最终结果。费用与责任工厂因文件间通常不同，不支持直接套用到整批。

## 输出

输出目录中会生成：

- `after_sales_annual_rollup.xlsx`：全局工作台结果中心首先展示的“售后全量汇总表”，版式匹配年度汇总参考模板，包含“汇总表”、逐年“售后统计表”和“输入文件对账”；每份输入文件固定保留一行，并按提出质量问题/报修日期排序及分年份统计。
- `after_sales_summary.xlsx`：保留既有分析、人工复核、按年份/月份/品牌统计和图表格式，不因独立年度汇总功能发生变化。
- `after_sales_records.json`：每个售后申请表抽取后的结构化明细。
- `after_sales_analysis.md`：与 Excel、JSON 使用同一结构化统计结果生成的售后分析报告和复核建议。
- `after_sales_analysis_report.docx`：排版后的 Word 售后分析报告，数字与 Excel、JSON 使用同一复核后数据源。
- `after_sales_brand_share.xlsx`：品牌方案件数量、占比明细和带分类/数量/百分比标签的饼图。
- `after_sales_reason_share.xlsx`：主要售后原因数量、占比明细和带分类/数量/百分比标签的饼图。
- `after_sales_monthly_fee.xlsx`：按年份逐月列示费用及案件数量；费用图保留 10,000 元红色预警线。
- `after_sales_yearly_dashboard.xlsx`：每个年份独立一页，上方并排显示品牌与售后原因占比，下方完整显示 1—12 月案件柱状图及月份、数量、图例。
- `result.json`：符合 BambooWorkbench 1.0 合同的运行结果、异常、待确认项和逐文件处理结果。

Excel 还包含“分析图表”工作表，展示月度案件趋势、多标签问题类型分布和企业售后成本趋势。没有有效数据时会显示中文说明，不生成空白图表。

## 统计规则

- 品牌：品牌与客户/项目严格分开；仅依据明确品牌证据识别，无法识别统一写 `未知`。未知品牌不会阻断原因、费用、已解决数量和汇总表生成。
- 售后原因：优先从客户反馈、售后调查、方案申请、责任落实和解决方案中提取具体原因；原表未写明根因时保留具体故障现象，不编造原因。
- 动态输入：只处理本次选择的文件；选择多少个 Excel，明细就保留多少条文件记录。重复内容也逐份处理，不会因哈希相同被跳过。
- 文件对账：无法读取或分析失败的文件仍写入明细并显示失败原因，但不会把未知数据计入业务汇总。
- 类型：按关键词识别 `性能`、`外观`、`加工`，一条售后可同时计入多个类型；分类标签分别统计，分类数量允许相加后大于案件总数。
- 人工复核：系统为售后费用、责任工厂和主投诉类型给出建议值，三项均为必审；人工确认的投诉类型会成为最终主分类，人工费用和责任工厂优先进入年度汇总与明细。
- 案件总数：每个成功解析且纳入汇总的文件/案件只计 1 次，不使用分类标签合计代替案件数。
- 企业售后成本：企业实际承担的补发、返工、赔偿、运费、人工和差旅等成本，兼容字段 `fee_amount` 与其完全等义。
- 内部责任扣款：内部人员或部门责任扣款，单独统计，不计入企业售后成本。
- 外部承担金额：供应商、合作方或其他外部主体承担的金额，单独统计，不计入企业售后成本。
- 金额识别：优先识别“总计/合计/共计”等最终金额，没有汇总金额时识别公式结果或明确分项；无法确定时保持空值，不以 0 元代替未知。
- 关闭数：根据解决方案、责任落实中是否出现“结案、完成、更换、返工、处理、达成一致”等闭环关键词判断。
- 输出脱敏：Excel、Markdown 和可外发明细 JSON 只写输入文件名，不写盘符、用户名、客户原始目录或临时目录。
- 文件隔离：损坏工作簿返回 `WORKBOOK_INVALID_OR_CORRUPTED` 和中文说明，其他正常文件继续处理。

业务关键词和同义字段在 `rules/default_rules.yaml` 中维护。

## 已知限制

- 自然语言费用抽取是规则法，遇到多个方案并列、金额没有写“元”、或只写数量未写单价时，需要人工复核。
- 日期只读取“提出质量问题日期、报修日期、投诉日期”等字段；只有月日时保留月日和空年份，并写入待确认项，不使用订单、交货或文件时间补齐。
- 图片、PDF 暂不作为正式输入，只处理 Excel 表。

## DeepSeek 与其他 AI 服务

桌面端不读取 API Key，也不直接访问 DeepSeek 或其他模型接口。模块先完成离线规则抽取，只对分类含糊、根因不清或多标签等确有语义辅助需要的案件生成统一 `service_requests`。竹简工作台负责选择提供商、展示脱敏预览、取得本次授权、调用模型并通过 `service_response_file` 返回结果。

对外载荷不包含客户字段、联系人、电话、邮箱、本机路径、原文件名或完整工作簿，只发送限长且再次脱敏的投诉摘要、规则候选类型、证据编号、费用候选和必要产品上下文。请求使用稳定候选编号和严格 JSON 合同；响应中的证据引用必须来自请求内给定的证据编号。

AI 只允许辅助 `性能/外观/加工/其他` 问题类型、具体原因摘要、证据引用和人工复核建议。品牌、售后费用、责任工厂、赔偿/责任认定、处理状态和结案状态不由 AI 决定。每份成功解析的 Excel 仍强制人工复核售后费用、责任工厂和投诉类型，人工值最终写入 Excel、JSON、图表和报告。

用户不授权、没有可用密钥、网络超时、限流、服务错误、响应缺失或 JSON 无效时，模块保留离线规则结果并继续人工复核和全批次导出，不漏掉任何已成功解析的文件。最终文件明确标注“AI辅助”“离线规则”或“AI降级”，不写入模型原始响应。

DeepSeek 和 OpenAI 兼容配置属于竹简工作台公共能力，应在系统设置中由框架安全保存；模块代码不会读取凭据或使用直连设计。

## 验证

模块自带的虚构 Excel 样例位于 `modules/after_sales/tests/fixtures/`，不包含真实企业数据。

PR #16 的人工构造脱敏输入位于
`tests/fixtures/acceptance/pr16_acceptance_sample.xlsx`；`samples/acceptance/` 只保留
Markdown、结构化 JSON、脱敏 `result.json` 和“分析图表”截图等非电子表格证据。
运行生成的 Excel 只在本地或 CI 临时目录验证，不提交进 Git。该样例在 `draft`
阶段预期返回 `needs_confirmation`，固定包含售后费用、责任工厂、投诉类型 3 项必审字段；
三类责任金额仍分别为 1000、200、300 元，完成 `finalize` 后返回 `success`。

在仓库根目录运行：

```powershell
python -m app.tools.module_contract_cli validate modules/after_sales
python -m pytest modules/after_sales/tests -q
python -m ruff check modules/after_sales
modules\after_sales\run_module.bat version
modules\after_sales\run_module.bat self-check
```
