# 水煮实验模块

`module_id: boiling`，版本 `1.1.1`，负责人 `anyuyu1`。

本模块读取 BambooWorkbench 任务 JSON 明确列出的 `.xlsx` 输入副本，抽取水煮实验字段，复算厚度、体积、密度、密度差与膨胀率，保留原表浸渍剥离结论，并生成结构化 `result.json`、汇总 Excel 和 Markdown 分析报告。

业务处理覆盖：

- 提取产品、规格、压制日期、班长、检测日期、浸胶日期和订单信息；
- 复核平均厚度、体积、密度、密度差和膨胀率；
- 提取浸渍剥离合格/不合格结论，支持 4/5/复测试件、端/中/数字编号和不同测点行数；
- 明确区分正常、异常、信息不足和待确认；
- 原表结论与规则观察冲突时保留两者并提示人工复核；
- 产品用途缺失时不选择膨胀率标准；
- 压制日期、班长、浸胶日期和订单信息缺失只提示待补，不阻断计算；
- 仅空表、未完成表或无可计算试件的文件不进入正常统计。

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

- `draft`：执行解析、复算和观察，一次性返回当前可确定的人工确认项；启用 AI 且确有候选时，另行产生需要逐次授权的脱敏 `service_requests`。
- `finalize`：完整消费 `confirmation_file` 和已授权的 `service_response_file`；产品用途支持一次确认后批量应用，依赖该答案新派生且不阻断成果的事项转为异常/观察项，不再发起第二轮确认。

AI 响应必须符合模块声明的严格 JSON 结构，并且只能引用请求中已有的候选和证据标识。拒绝授权、无密钥、断网、超时、限流、非法 JSON 或证据不匹配时，模块继续生成完整离线成果并在报告中说明降级原因。AI 内容只进入人类报告，不进入结构化业务记录，也不改变公式、阈值、原始值、规则命中、业务状态或人工结论。

规则版本为 `2026.07.18-v0.1`：每个有效试件密度须在 `1.1～1.3 g/cm³`（含边界），密度差须 `≤0.1 g/cm³`（含边界）；膨胀率按产品用途执行。墙板/栏杆 `>6.5% 且 <8%` 在本版转人工复核，不自动标色。具体规则和权限边界见 `docs/`。

## 历史数据适配

已对 41 份四月历史表进行只读回归：识别 193 个试件，覆盖 A:H、A:I、A:J 等有效区域以及 4/5/复测布局。`20260132.xlsx` 无有效测量块，`2026112.xlsx` 同时缺检测日期和检测结论，因此作为信息不足单列；真实企业原表及其绝对路径不进入仓库。

## 输出

- `result.json`：符合 `contracts/schemas/module-result.schema.json` 的机器结果。
- `boiling_summary.xlsx`：正常汇总、未纳入正常统计清单、试件明细、规则说明和分析图表。
- `boiling_analysis.xlsx`：面向业务人员的易读分析报告，完整关注项集中在独立工作表。
- `boiling_analysis.md`：按运行概况、总体结论、关键指标、异常明细、风险汇总和下一步建议整理的文字摘要；正常文件不逐条堆叠。
- `boiling_records.json`：包含四类业务状态、原表值、复算值、规则观察和冲突信息的机器可读记录。

三类正式业务成果只记录来源文件名、工作表和单元格，不记录用户电脑绝对路径；`result.json` 仍按框架合同保留输入和输出绝对路径。

## 验证

在仓库根目录执行：

```powershell
python -m app.tools.module_contract_cli validate modules/boiling
python -m pytest modules/boiling/tests -q
powershell -ExecutionPolicy Bypass -File scripts/verify_repo.ps1
```

脱敏样例位于仓库 `modules/boiling/tests/fixtures/samples/input/`，对应机器预期位于 `samples/expected/`。测试还会动态构造 41 份脱敏历史结构回归样本（39 份纳入统计、2 份信息不足），校验 processed/failed/skipped 总数守恒及输入 SHA-256 未变化，并通过真实 `TaskService` 验证一次确认闭环。正式交付不包含真实企业 Excel、运行日志、数据库、密钥、客户路径或接口响应。
