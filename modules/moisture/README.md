# 竹丝水分检测模块

BambooWorkbench 竹丝水分检测模块 v1.0.1。模块提供两条相互隔离的业务路径：

- 普通汇总：确定性 Excel 解析、统计、规则初筛和四表成果；
- 独立 AI 报告：用户主动选择当前汇总表、可选历史资料和 approved 经验后，由主框架在逐次同意下调用 Provider。

模块不直接访问网络、Provider、数据库或凭据，AI 结果不修改汇总表、规则颜色或确定性结论。

## 快速使用

### 客户安装版

从竹简工作台选择“竹丝水分检测”：

1. 普通检测选择一个或多个原始 `.xlsx`，按提示确认缺失的业务年份；
2. 在结果中心打开 `moisture_summary.xlsx` 和 `analysis_report.md`；
3. 需要进一步分析时，另行打开“AI 汇总报告”，选择当前汇总表、历史资料、approved 经验并输入问题；
4. 查看脱敏预览并逐次同意后，结果中心显示独立的 AI Markdown/JSON 成果。

客户安装版自带 `runtime/BambooMoistureModule.exe`，不需要安装 Python。

### 源码开发环境

所有 Python 命令必须显式使用当前仓库 `.venv`：

```powershell
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable); print(sys.version)"
.\.venv\Scripts\python.exe -m pytest --version
.\.venv\Scripts\python.exe -m app
```

不得使用裸 `python`、`py`、系统 Python或全局依赖。

`jsonschema` 是模块的 Schema 校验依赖；紧随其后的 `requirements.txt` 安装命令会安装该依赖。

## 输入与输出

普通汇总支持一个或多个原始 `.xlsx`，不会修改输入文件。输出包括：

- `result.json`：最后原子写入的机器合同结果；
- `moisture_summary.xlsx`：按检测日期升序排列的四表工作簿；
  - **竹丝含水率统计**（19列）；
  - **异常分析明细**；
  - **趋势分析**（含散点/趋势图）；
  - **来源追溯**；
- `analysis_report.md`：面向客户的确定性业务摘要；正常批次聚合展示，异常、失败和待复核批次详细展开，
  规则哈希、内部来源及完整引用集中在文末技术附录。

v1.0.1 不再生成“模型分析记录”，普通汇总也不再声明 AI 辅助复判请求。橙色表示确定性偏高疑似，绿色表示确定性偏低疑似；区间值大于 13% 时按当前规则染橙色。`0.55/0.47` 均值阈值仍待业务批准，不得称为正式生产标准。

独立 AI 报告输出：

- 合法响应：`ai_analysis_report.md` 和 `ai_analysis_result.json`；
- denied、error、timeout 或非法响应：仅生成结构化降级结果，不伪造 AI 报告；
- 原汇总表 SHA-256 始终不变。

历史资料兼容模块生成的 v1.0.1 四表和 v1.0.0 五表文件；旧五表中的“模型分析记录”只读忽略，不参与新分析。

## 运行与管理命令

主框架正式任务经 Registry → TaskService → Runner → BAT 启动：

```powershell
modules\moisture\run_module.bat version
modules\moisture\run_module.bat self-check
modules\moisture\run_module.bat run --job C:\absolute\path\to\job.json
```

历史资料和 approved 经验目录由主框架通过独立管理入口调用：

```powershell
modules\moisture\run_management.bat manage --request C:\absolute\request.json --response C:\absolute\response.json
```

不要把管理命令加入普通 draft/finalize。`run_module.bat` 和 `run_management.bat` 均优先使用显式冻结程序、已激活环境或仓库 `.venv`，不会从 PATH 盲选系统 Python。

## 常见错误

| 症状 | 原因/处理 |
| --- | --- |
| `WORKBOOK_STRUCTURE_INVALID` | 原始 Excel 或历史汇总表结构不受支持；核对工作表和表头 |
| `SAMPLE_LIMIT_EXCEEDED` | 当前每个工作簿仅支持 1—10 个样本 |
| draft 为 `needs_confirmation` | 日期只有月/日；输入四位业务年份后 finalize |
| 批次为 `partial_success` | 部分文件损坏；正常文件仍会处理 |
| AI 结果为 denied/error/timeout | 主框架未授权或 Provider 故障；确定性汇总不受影响 |
| AI 没有 Markdown | 响应未通过严格校验；查看结构化降级 JSON |
| 历史资料无法导入 | 检查是否为模块生成的标准四表或兼容五表文件 |

## 构建和验证

```powershell
.\.venv\Scripts\python.exe -m app.tools.module_contract_cli validate modules/moisture
modules\moisture\run_module.bat version
modules\moisture\run_module.bat self-check
.\.venv\Scripts\python.exe -m pytest modules\moisture\tests -q
powershell -ExecutionPolicy Bypass -File modules\moisture\build_portable_runtime.ps1
```

不得提交 `.exe`、`runtime/`、`build/`、`dist/`、`.venv`。

## 当前验收状态

- 模块全量测试：418 passed；
- Ruff、合同 CLI、Schema 同步、`version=1.0.1`、`self-check=ok`：通过；
- 完整便携构建及 portable verification：通过；
- 冻结 EXE 经真实 Registry/TaskService/Runner 的普通汇总、AI 报告和管理入口闭环：5 passed；
- 当前 PR #41 指向 `integration`，已进入负责人评审，尚未合并。

GitHub Actions 当前红叉不是代码失败：`quality` job 因仓库账户付款失败或 Actions
spending limit 不足，在 Runner 分配前即被 GitHub 拒绝启动（无任何测试步骤）。
仓库负责人处理 Billing 后重新运行即可；不得通过修改模块或工作流掩盖该外部阻塞。

## 当前指导文档

| 文档 | 内容 |
| --- | --- |
| [业务规则与数据说明](docs/业务规则与数据说明.md) | 字段、公式、统计、阈值、颜色、经验与 AI 边界 |
| [架构与开发维护指南](docs/架构与开发维护指南.md) | 调用链、合同、管理入口、测试和禁止项 |
| [验收标准与已知限制](docs/验收标准与已知限制.md) | 合同、业务、框架、安全、降级和限制 |

## 设计、交接与记录

| 文档 | 内容 |
| --- | --- |
| [三功能简化架构](docs/architecture/moisture-next-stage-architecture.md) | 汇总生产、独立 AI 报告和后续规则治理方向 |
| [v1.0.1 独立 AI 报告计划](docs/architecture/moisture-v1.0.1-independent-ai-report-plan.md) | 本版本模块实施边界 |
| [框架适配请求](docs/framework-change-requests/FCR-moisture-20260723-ai-report-context-selection.md) | 已由框架 PR #43 实施的最小适配 |
| [框架事项状态](docs/framework-issues.md) | 尚待业务/发布负责人处理的事项 |
| [CHANGELOG](CHANGELOG.md) | 版本变更 |
| [验收证据](docs/evidence/) | 测试和人工验收记录 |
| [历史归档](docs/archive/) | 不作为当前实现依据的旧方案 |
