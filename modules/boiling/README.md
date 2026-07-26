# 水煮实验模块

`module_id: boiling`，版本 `1.3.0`，负责人 `anyuyu1`。

本模块读取 BambooWorkbench 任务 JSON 明确列出的 `.xlsx` 输入副本，抽取水煮实验字段，复算厚度、体积、密度、密度差与膨胀率，保留原表浸渍剥离结论，并生成结构化 `result.json`、汇总 Excel 和 Markdown 分析报告。

业务处理覆盖：

- 提取产品、规格、压制日期、班长、检测日期、浸胶日期和订单信息；
- 复核平均厚度、体积、密度、密度差和膨胀率；
- 提取浸渍剥离合格/不合格结论，支持 4/5/复测试件、端/中/数字编号和不同测点行数；
- 明确区分正常、异常、信息不足和待确认；
- 原表结论与规则观察冲突时保留两者并提示人工复核；
- 不再创建人工开裂检查确认项；膨胀率等级按现有规则直接输出，源表内容原样保留；
- 产品用途缺失时不选择膨胀率标准；
- 压制日期、班长、浸胶日期和订单信息缺失只提示待补，不阻断计算；
- 仅空表、未完成表或无可计算试件的文件不进入正常统计。
- 可直接上传两个月及以上由本模块生成的“水煮检测汇总”文件，按检测月份生成密度、膨胀率、异常数及环比趋势。
- 多月趋势会生成模块专用 AI 服务请求，并检索工作台 `boiling` 知识库；二者只补充分析建议，不改变原有公式、阈值、等级或业务状态。

模块不包含独立 GUI、定时运行或目录扫描功能；不修改输入文件、不自行联网、不保存 API Key、不创建子进程，只写任务声明的 `output_dir`。启用 AI 时，模块仅通过工作台统一服务合同提交脱敏摘要，由框架在展示脱敏预览并取得用户授权后调用 DeepSeek、OpenAI 兼容接口或离线模拟服务；AI 结果只用于辅助说明，不改变确定性业务判定。

## 免环境便携运行

仓库便携版构建会调用 `modules/boiling/build_portable_runtime.ps1`，在
`dist/BambooWorkbench/modules/boiling/runtime/` 生成独立运行时。生成物只用于交付，
不得提交到 Git。便携目录中的 `run_module.bat` 会优先运行本模块的
`runtime/boiling_module.exe`，目标电脑无需安装 Python。

单独重复构建及验证本模块运行时：

```powershell
powershell -ExecutionPolicy Bypass -File modules/boiling/build_portable_runtime.ps1
```

构建脚本会在无 Python 的隔离 `PATH` 下验证 `version`、`self-check` 以及一次
`draft -> confirmation -> finalize` 业务闭环。找不到便携运行时和 Python 时，
`run_module.bat` 固定返回退出码 `4`；便携运行时存在时，子进程退出码会原样返回。

## 安装依赖

```powershell
python -m pip install -r modules/boiling/requirements.txt
```

## 命令

```powershell
modules\boiling\run_module.bat version
modules\boiling\run_module.bat self-check
modules\boiling\run_module.bat run --job D:\absolute\path\job.json
```

## 任务阶段

- `draft`：执行解析、复算和观察，一次性返回当前可确定的人工确认项；确有规则候选或至少两个月趋势数据时，产生需要逐次授权的脱敏 AI `service_requests`。多月趋势还会通过统一合同检索水煮知识库。
- `finalize`：完整消费 `confirmation_file` 和已授权的 `service_response_file`；产品用途支持一次确认后批量应用，依赖该答案新派生且不阻断成果的事项转为异常/观察项，不再发起第二轮确认。

AI 响应必须符合模块声明的严格 JSON 结构，并且只能引用请求中已有的候选和证据标识。拒绝授权、无密钥、断网、超时、限流、非法 JSON 或证据不匹配时，模块继续生成完整离线成果并在报告中说明降级原因。AI 内容只进入人类报告，不进入结构化业务记录，也不改变公式、阈值、原始值、规则命中、业务状态或人工结论。

为降低真实 AI 的超时和截断概率，极速模式单次只发送最高优先级的 1 个候选，负载上限为 12 KiB，并按多月趋势、严重异常、结论/计算冲突和浸渍剥离关注项排序。未发送候选仍完整保留在离线 Excel、Markdown 和 JSON 中，不会被遗漏或改变业务状态。

## 月度快照与年度累计

单一检测月份的成功 `finalize` 会额外生成内部 `boiling_monthly_snapshot.json`。快照采用 `module-owned-v1` 信封，保存最终人工值、业务记录、异常、冲突以及本月已经取得的 AI/知识库建议；业务负载中的来源文件只保留文件名，不保留绝对路径。当前模块不再为新任务创建人工开裂检查确认，但对历史快照中已有的 `crack_inspection_confirmed` 和 `crack_inspection_status` 字段原样累计，不再次询问或推断。

框架按同年月份升序准备快照后，可调用模块离线累计入口：

```powershell
modules\boiling\run_module.bat rollup `
  --request D:\authorized\rollup-request.json `
  --response D:\authorized\staging\rollup-response.json
```

累计请求必须显式设置 `forbid_network=true`，并提供快照授权根、目标年月、已有正式快照、当前候选快照、逐文件 SHA-256 和规则配置身份。模块允许月份缺口；拒绝跨年、乱序、重复月份、晚于目标月、路径越界和哈希不一致。候选快照与已有快照同月时替换旧月后重算，累计输出包括完整 Excel 汇总、Excel 分析报告、Markdown 报告、图表和结构化业务记录，`network_call_count` 固定为 `0`。

模块自有合同位于 `schemas/`。现有 v1.2.0 框架尚未提供任务年月、月度槽位、原子替换事务和确认项 `learning` 公共字段，完整接入要求见 `docs/framework-change-requests/FCR-boiling-20260726-monthly-rollup-framework.md`；在框架适配前，普通 draft/finalize 保持兼容，累计入口可独立复验。

规则版本为 `2026.07.18-v0.1`：每个有效试件密度须在 `1.1～1.3 g/cm³`（含边界），密度差须 `≤0.1 g/cm³`（含边界）；膨胀率按产品用途执行。墙板/栏杆 `>6.5% 且 <8%` 在本版转人工复核，不自动标色。具体规则和权限边界见 `docs/`。

## 历史数据适配

已对 41 份四月历史表进行只读回归：识别 193 个试件，覆盖 A:H、A:I、A:J 等有效区域以及 4/5/复测布局。`20260132.xlsx` 无有效测量块，`2026112.xlsx` 同时缺检测日期和检测结论，因此作为信息不足单列；真实企业原表及其绝对路径不进入仓库。

## 输出

- `result.json`：符合 `contracts/schemas/module-result.schema.json` 的机器结果。
- `boiling_summary.xlsx`：正常汇总、未纳入正常统计清单、试件明细、规则说明和分析图表。
- `boiling_analysis.xlsx`：面向业务人员的易读分析报告，完整关注项集中在独立工作表。
- `boiling_analysis.md`：按运行概况、总体结论、关键指标、异常明细、风险汇总和下一步建议整理的文字摘要；正常文件不逐条堆叠。
- `boiling_records.json`：包含四类业务状态、原表值、复算值、规则观察和冲突信息的机器可读记录。

多月趋势输入必须包含“水煮检测汇总”工作表，以及“检测日期”和至少一个“平均密度/平均膨胀率”列。只有一个可识别月份时仍生成离线趋势表，但不请求 AI 或知识库；两个月及以上才产生趋势候选。月份总体均值可能受规格构成变化影响，报告会明确提示按同规格复核，不能据此直接认定工艺原因。

三类正式业务成果只记录来源文件名、工作表和单元格，不记录用户电脑绝对路径；`result.json` 仍按框架合同保留输入和输出绝对路径。

## 验证

在仓库根目录执行：

```powershell
python -m app.tools.module_contract_cli validate modules/boiling
python -m pytest modules/boiling/tests -q
powershell -ExecutionPolicy Bypass -File scripts/verify_repo.ps1
```

脱敏样例位于仓库 `modules/boiling/tests/fixtures/samples/input/`，对应机器预期位于 `samples/expected/`。测试还会动态构造 41 份脱敏历史结构回归样本（39 份纳入统计、2 份信息不足），校验 processed/failed/skipped 总数守恒及输入 SHA-256 未变化，并通过真实 `TaskService` 验证一次确认闭环。正式交付不包含真实企业 Excel、运行日志、数据库、密钥、客户路径或接口响应。
