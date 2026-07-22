# 售后统计模块（1.5.0）

本模块是售后 Excel 智能汇总网站的业务处理核心，已整理为 BambooWorkbench 的 `after_sales` 模块包。它从售后申请 Excel 中抽取客户、地点、销售、产品、订单、报修日期、反馈、调查、方案、三类金额和处理状态，并按参考模板生成品牌/月度汇总、逐年售后明细、图表与分析报告。1.5.0 通过统一工作台 AI 网关声明 DeepSeek/OpenAI 兼容分析请求，不在模块中保存 API Key。

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

1.5.0 的统一模块入口会先逐份读取 Excel，并把反馈、方案申请明细、售后调查、最终方案和责任落实整理为最小必要文本；手机号、邮箱和本地路径在模块侧先脱敏，再交给框架统一脱敏和联网预览。模块按固定字节预算分批，100 份文件仍保留 100 个唯一案件编号，AI 响应必须逐一覆盖且不得增加、遗漏或重复案件。

在竹简工作台“系统设置”中选择“DeepSeek”或“OpenAI 兼容”，填写接口地址、模型和 API Key，并保存到系统安全凭据存储。运行售后任务时，工作台会显示脱敏预览，只有用户选择“允许”才会联网。API Key 不进入 `job.json`、模块进程、日志、Excel 或 Git 仓库。

模块把 AI 用于品牌候选、具体根因、性能/外观/加工分类、责任工厂、最终方案费用候选和解决状态。确定性费用复核和人工确认始终高于模型结果；拒绝联网、超时、服务错误、无效 JSON 或案件覆盖不完整时，只降级对应文件为离线建议并继续人工复核，不会漏掉输入文件，也不会把未知费用写成 0。

现有框架在同一次确认提交后才执行 AI，因此当前页面的三项业务复核建议仍来自离线草稿，AI 结果会在最终分析中安全补充，人工填写值仍最终生效。要让用户先看到 AI 结果再复核，需由框架方实施 `docs/framework-change-requests/FCR-after_sales-20260722-ai-preanalysis-review.md` 所述的多阶段工作流；模块没有越权修改公共框架。

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
