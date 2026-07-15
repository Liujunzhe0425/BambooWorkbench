# 售后统计模块（1.3.1）

本模块是售后 Excel 智能汇总网站 1.3.1 的业务处理核心，已整理为 BambooWorkbench 的 `after_sales` 模块包。它从售后申请 Excel 中抽取客户、地点、销售、产品、订单、报修日期、反馈、调查、方案、费用和关闭信息，并按年份、月份、品牌、问题类型生成汇总表。

本目录只包含处理引擎、规则、模板、脱敏样本、测试和交接文档；不包含独立网页、运行日志、客户原表、API Key 或本机绝对路径。1.3.1 的 Excel 分析与导出算法未作改动，仓库适配只涉及统一模块合同与启动入口。

## 运行环境

- Windows 10/11
- Python 3.10 或更高版本
- 依赖见 `requirements.txt`
- 规则模式不需要网络；启用 AI 分析时需要 OpenAI API Key 和网络

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
- `result.json`：符合 BambooWorkbench 1.0 合同的运行结果、异常、待确认项和逐文件处理结果。

## 统计规则

- 品牌：品牌与客户/项目严格分开；仅依据明确品牌证据识别，无法识别统一写 `未知`。未知品牌不会阻断原因、费用、已解决数量和汇总表生成。
- 售后原因：优先从客户反馈、售后调查、方案申请、责任落实和解决方案中提取具体原因；原表未写明根因时保留具体故障现象，不编造原因。
- 动态输入：只处理本次选择的文件；选择多少个 Excel，明细就保留多少条文件记录。重复内容也逐份处理，不会因哈希相同被跳过。
- 文件对账：无法读取或分析失败的文件仍写入明细并显示失败原因，但不会把未知数据计入业务汇总。
- 费用：AI检查完整工作簿，逐项提取材料、人工、差旅、运费、返工、补发和赔偿金额，并保留费用依据；若AI漏掉原文明示总额，规则抽取会自动恢复。
- 类型：按关键词识别 `性能`、`外观`、`加工`，一条售后可同时计入多个类型。
- 费用：优先识别“总计/合计/共计/费用计算”等汇总金额；没有汇总金额时识别公式结果或费用明细。包含“转嫁给供应商/合作方”等语义的费用不纳入统计。
- 关闭数：根据解决方案、责任落实中是否出现“结案、完成、更换、返工、处理、达成一致”等闭环关键词判断。

业务关键词和同义字段在 `rules/default_rules.yaml` 中维护。

## 已知限制

- 自然语言费用抽取是规则法，遇到多个方案并列、金额没有写“元”、或只写数量未写单价时，需要人工复核。
- 日期只读取“提出质量问题日期、报修日期、投诉日期”等字段；只有月日时保留月日和空年份，并写入待确认项，不使用订单、交货或文件时间补齐。
- 图片、PDF 暂不作为正式输入，只处理 Excel 表。

## DeepSeek 边界

原 1.3.1 核心保留了 DeepSeek 结构化分析适配代码和回归测试。按照 BambooWorkbench 安全边界，统一模块入口不会读取框架凭据，也不会从 `job.json` 接收 API Key；没有 AI 授权或网络时仍会完成规则分析与 Excel 汇总。后续如由框架负责人接入统一 AI 服务，应通过 `service_requests` 与脱敏授权流程完成，不应把密钥写入本模块。

## 验证

在仓库根目录运行：

```powershell
python -m app.tools.module_contract_cli validate modules/after_sales
python -m pytest modules/after_sales/tests -q
modules\after_sales\run_module.bat self-check
```
