# 售后统计模块（1.3.1）

本模块是售后 Excel 智能汇总网站 1.3.1 的业务处理核心，已整理为 BambooWorkbench 的 `after_sales` 模块包。它从售后申请 Excel 中抽取客户、地点、销售、产品、订单、报修日期、反馈、调查、方案、三类金额和处理状态，并按年份、月份、品牌和多标签问题类型生成汇总、图表与分析报告。

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

框架会在 `input_files` 中传入只读 Excel 副本的绝对路径。模块不会修改、删除或重命名输入文件，只向 `output_dir` 写入结果。`finalize` 阶段会读取 `confirmation_file`，并把品牌、报修日期、主原因、费用及案件状态等人工复核值写入最终结果。

## 输出

输出目录中会生成：

- `after_sales_summary.xlsx`：年度售后统计表，包含按品牌、月份、问题类型、费用和关闭数的汇总，以及结构化明细表。
- `after_sales_records.json`：每个售后申请表抽取后的结构化明细。
- `after_sales_analysis.md`：与 Excel、JSON 使用同一结构化统计结果生成的售后分析报告和复核建议。
- `result.json`：符合 BambooWorkbench 1.0 合同的运行结果、异常、待确认项和逐文件处理结果。

Excel 还包含“分析图表”工作表，展示月度案件趋势、多标签问题类型分布和企业售后成本趋势。没有有效数据时会显示中文说明，不生成空白图表。

## 统计规则

- 品牌：品牌与客户/项目严格分开；仅依据明确品牌证据识别，无法识别统一写 `未知`。未知品牌不会阻断原因、费用、已解决数量和汇总表生成。
- 售后原因：优先从客户反馈、售后调查、方案申请、责任落实和解决方案中提取具体原因；原表未写明根因时保留具体故障现象，不编造原因。
- 动态输入：只处理本次选择的文件；选择多少个 Excel，明细就保留多少条文件记录。重复内容也逐份处理，不会因哈希相同被跳过。
- 文件对账：无法读取或分析失败的文件仍写入明细并显示失败原因，但不会把未知数据计入业务汇总。
- 类型：按关键词识别 `性能`、`外观`、`加工`，一条售后可同时计入多个类型；分类标签分别统计，分类数量允许相加后大于案件总数。
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

## DeepSeek 边界

原 1.3.1 核心保留了 DeepSeek 结构化分析适配代码和回归测试。按照 BambooWorkbench 安全边界，统一模块入口不会读取框架凭据，也不会从 `job.json` 接收 API Key；`ai_enabled=false` 或没有框架授权响应时直接完成离线规则分析，且不生成 `api_config` 人工确认。后续统一 AI/知识库能力只能通过框架负责人定义的授权接口接入，不得把密钥写入本模块或绕过框架联网。

## 验证

模块自带的虚构 Excel 样例位于 `modules/after_sales/tests/fixtures/`，不包含真实企业数据。

在仓库根目录运行：

```powershell
python -m app.tools.module_contract_cli validate modules/after_sales
python -m pytest modules/after_sales/tests -q
modules\after_sales\run_module.bat self-check
```
