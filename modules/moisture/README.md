# 竹丝水分检测模块

BambooWorkbench 竹丝水分检测模块 v1.3.1。模块提供确定性普通汇总、独立
AI 报告，以及由主框架编排的月度快照与年度累计：

- 普通汇总：确定性 Excel 解析、统计、规则初筛和四表成果；
- 独立 AI 报告：用户主动选择当前汇总表、可选历史资料和 approved 经验后，
  由主框架按系统全局联网默认调用或拒绝 Provider。

模块不直接访问网络、Provider、数据库或凭据，AI 结果不修改汇总表、规则颜色或确定性结论。

> v1.3.1 在既有历史追加、经验/规则管理和规则快照基础上，提供 finalize
> 月度快照、完全离线年度累计和可选确认学习描述。
> 日常管理从“竹丝水分检测”页面进入“打开经验与规则管理”；发布前必须核对版本与完整
> SHA-256。详细步骤见[经验与规则管理使用教程](docs/经验与规则管理使用教程.md)。

## 快速使用

### 客户安装版

从竹简工作台选择“竹丝水分检测”：

1. 普通检测选择一个或多个原始 `.xlsx`，按提示确认缺失的业务年份；
2. 在结果中心打开 `moisture_summary.xlsx` 和 `analysis_report.md`；
3. 需要进一步分析时，另行打开“AI 汇总报告”，选择当前汇总表、历史资料、approved 经验并输入问题；
4. 系统继续执行脱敏和授权审计；全局联网允许时生成独立 AI Markdown/JSON，
   拒绝或服务异常时生成结构化降级结果。

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

当前 v1.3.1 不生成“模型分析记录”，普通汇总也不声明 AI 辅助复判请求。橙色表示确定性偏高疑似，绿色表示确定性偏低疑似；区间值大于 13% 时按当前规则染橙色。`0.55/0.47` 均值阈值仍待业务批准，不得称为正式生产标准。

独立 AI 报告输出：

- 合法响应：`ai_analysis_report.md` 和 `ai_analysis_result.json`；
- denied、error、timeout 或非法响应：仅生成结构化降级结果，不伪造 AI 报告；
- 原汇总表 SHA-256 始终不变。

历史资料兼容模块生成的 v1.1.1/1.1.0/1.0.1 四表和 v1.0.0 五表文件；旧五表中的“模型分析记录”只读忽略，不参与新分析。

## 运行与管理命令

主框架正式任务经 Registry → TaskService → Runner → BAT 启动：

```powershell
modules\moisture\run_module.bat version
modules\moisture\run_module.bat self-check
modules\moisture\run_module.bat run --job C:\absolute\path\to\job.json
modules\moisture\run_module.bat rollup --request C:\absolute\rollup-request.json --response C:\absolute\output\rollup-result.json
```

`rollup` 只接受主框架生成的绝对路径公共请求，并要求
`BAMBOO_OFFLINE=1`。模块重新校验快照大小和 SHA-256 后，按同年目标月之前
的已确认快照生成累计 `moisture_summary.xlsx`、`analysis_report.md` 和
`moisture_business_records.json`。累计过程不访问网络、不调用 AI，也不重新
发起人工确认。

历史资料、经验治理和规则治理统一通过独立管理入口调用：

```powershell
modules\moisture\run_management.bat manage --request C:\absolute\request.json --response C:\absolute\response.json
```

公开管理合同支持：

- 历史资料：导入、列出和停用；
- 经验三栏：列出、查看、校验、创建/更新草稿、发布、停用和历史复制；
- 规则三栏：列出、查看、校验、预览、创建/更新草稿、发布、停用、恢复和历史复制；
- 当前规则只读查询：返回严格的 `{version, sha256}`。

新操作使用统一 v1.1 request/response Schema；旧 v1.0 四操作保留迁移兼容。完整操作名、
参数和示例见[经验与规则管理使用教程](docs/经验与规则管理使用教程.md)及
[`samples/management/`](samples/management/)。

当前模块不提供 AI 候选规则生成功能。规则草稿由有权限的业务人员创建、校验并确认发布，
AI 报告不会创建、修改或发布规则。

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

- 模块公开版本：`1.3.1`；
- 历史追加继续保持 `supports_incremental: true`；
- 统一管理进程覆盖 27 个公开操作，并保留旧 v1.0 四操作；
- 主框架经验/规则管理页面通过 ManagementService/Runner 调用独立管理进程；
- TaskService 创建任务时固定 `{version, sha256}`，draft/finalize 不重新选择 active；
- v1.3.1 私有月度快照支持稳定、安全的 Unicode 业务记录 ID；源文件名生成 ID
  时清除首尾 Unicode 空白，内部空格保持不变。规范化后冲突会整批失败且不覆盖
  任何记录；公共 Schema、finalize 快照、离线累计和确认学习适配保持不变；
- 框架 PR #68 已解除月度 Runner 和非月度 AI report 快照边界阻塞；
- 真实月度累计、全局 AI 允许/拒绝和离线降级均纳入模块框架回归。

## 当前指导文档

| 文档 | 内容 |
| --- | --- |
| [经验与规则管理使用教程](docs/经验与规则管理使用教程.md) | GUI 入口、经验编辑、规则发布、停用、恢复和错误处理 |
| [业务规则与数据说明](docs/业务规则与数据说明.md) | 字段、公式、统计、阈值、颜色、经验与 AI 边界 |
| [架构与开发维护指南](docs/架构与开发维护指南.md) | 调用链、合同、管理入口、测试和禁止项 |
| [验收标准与已知限制](docs/验收标准与已知限制.md) | 合同、业务、框架、安全、降级和限制 |

## 状态、交接与记录

| 文档 | 内容 |
| --- | --- |
| [框架事项状态](docs/framework-issues.md) | 尚待业务/发布负责人处理的事项 |
| [框架适配请求模板](docs/框架适配请求模板.md) | 后续确需修改主框架时使用的请求模板 |
| [主框架后续更新要求](../../docs/handoff/模块后续更新与兼容接入验收说明.md) | 分支、修改边界、测试和 PR 要求 |
| [CHANGELOG](CHANGELOG.md) | 版本变更 |
| [验收证据](docs/evidence/) | 测试和人工验收记录 |
| [历史归档](docs/archive/) | 旧计划、已完成 FCR 和迁移记录；不作为当前实现依据 |
