# 售后统计模块（1.6.4）

本模块是售后 Excel 智能汇总网站的业务处理核心，已整理为 BambooWorkbench 的 `after_sales` 模块包。它从售后申请 Excel 中抽取客户、地点、销售、产品、订单、报修日期、反馈、调查、方案、三类金额和处理状态。1.6.4 保留售后专属 DeepSeek/OpenAI 兼容配置与逐文件人工复核流程，最终输出一个按报修时间连续排序的全量总表、Word 分析报告、三类独立可视化图表和年度图表总览。

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

Windows 便携包会在模块目录的 `runtime` 中携带独立运行时；未显式设置
`PYTHON_EXE` 时，`run_module.bat` 会使用该运行时，不依赖使用者电脑上的 Python
或第三方库。框架便携版构建完成后，
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

- `after_sales_master_summary.xlsx`：只包含一个“售后全量总表”工作表；每个输入文件固定保留一行，按完整提出质量问题/报修日期排序，左侧保留原表内容，右侧追加售后问题分析、原因、复核后的费用、责任工厂与处理状态。
- `after_sales_analysis_report.docx`：经过版式设计的 Word 售后分析报告。
- `after_sales_brand_share.xlsx`：品牌方案件数量与占比表及二维圆环图。
- `after_sales_reason_share.xlsx`：人工复核后主要售后原因的数量与占比表及二维圆环图。
- `after_sales_monthly_fee.xlsx`：按年份逐月列示费用的明细表和柱线组合图；蓝色柱为当月费用，红线固定为 10,000 元。
- `after_sales_yearly_dashboard.xlsx`：每个年份一张统计看板，上方并排显示品牌案件占比和售后原因占比，下方完整显示 1—12 月售后反馈数量；月份横轴、数量纵轴、柱顶数值、图例、分类数量和百分比均明确标注。
- `result.json`：符合 BambooWorkbench 1.0 合同的运行结果、异常、待确认项和逐文件处理结果。

模块仍会在输出目录保存不向结果中心展示的内部复核状态，用于草稿与最终提交之间复用 AI 快照和人工确认值；网站不会再出现“售后结构化明细”的下载按钮。

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
- 输出脱敏：Excel 和 Word 只写输入文件名，不写盘符、用户名、客户原始目录或临时目录。
- 文件隔离：损坏工作簿返回 `WORKBOOK_INVALID_OR_CORRUPTED` 和中文说明，其他正常文件继续处理。

业务关键词和同义字段在 `rules/default_rules.yaml` 中维护。

## 已知限制

- 自然语言费用抽取是规则法，遇到多个方案并列、金额没有写“元”、或只写数量未写单价时，需要人工复核。
- 日期只读取“提出质量问题日期、报修日期、投诉日期”等字段；只有月日时保留月日和空年份，并写入待确认项，不使用订单、交货或文件时间补齐。
- 图片、PDF 暂不作为正式输入，只处理 Excel 表。

## DeepSeek 与其他 AI 服务

售后任务页直接显示“售后专用 AI 智能分析”配置区，可选择 DeepSeek 或其他 OpenAI 兼容接口，填写 HTTPS 接口地址、模型和 API Key。点击“开始智能分析并进入人工复核”就是本批次的明确联网授权，因此待确认页不会再出现“允许/拒绝”选项，也不会把内部请求 JSON 当作业务复核内容。DeepSeek 推荐使用 `https://api.deepseek.com` 和 `deepseek-v4-flash`；复杂案件可选 `deepseek-v4-pro`。

API Key 以售后专属条目保存在 Windows 凭据库，不进入 `job.json`、结果、日志、Excel、安装包或 Git。只有从售后页面点击开始的草稿任务会读取该凭据；测试、自检、其他模块和最终导出阶段不会读取。最终导出复用草稿期已经校验的 AI 结构化快照，不会再次调用付费接口。

模块把 AI 用于品牌候选、具体根因、性能/外观/加工分类、责任工厂、最终方案费用候选和解决状态。AI 建议完成后，每份 Excel 的复核项集中展示，售后费用、责任工厂和投诉类型必须人工确认；人工值覆盖 AI 和规则值。接口超时、服务错误或无效 JSON 时只把对应文件降级为规则建议并继续复核，不漏文件、不把未知费用写成 0。

模块目录中同时提交 `docs/framework-change-requests/FCR-after_sales-20260723-module-local-ai-config.md`，供框架负责人正式审核售后任务页配置和启动授权交互；公共框架页面改动不纳入模块 PR。

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
modules\after_sales\run_module.bat self-check
```
