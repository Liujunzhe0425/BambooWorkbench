# 竹丝水分检测模块

BambooWorkbench 竹丝水分检测模块 v0.1.0。模块通过主框架 Registry 发现，
由 Runner 经 `run_module.bat` 启动，支持确定性 Excel 分析、draft/finalize、
业务确认项以及受控的 knowledge/AI service request。模块不直接访问网络、
Provider、数据库或凭据。

## 环境与安装

- Windows
- Python 3.11 或更高版本（当前仓库同时在 Python 3.12 验证）

所有开发和测试命令必须显式使用当前 BambooWorkbench 仓库的虚拟环境：

```powershell
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable); print(sys.version)"
.\.venv\Scripts\python.exe -m pytest --version
.\.venv\Scripts\python.exe -m pip install -r modules\moisture\requirements.txt
```

不得使用裸 `python`、`py`、系统 Python 或全局安装的依赖。启动器选择解释器的
顺序为 `BAMBOO_MODULE_PYTHON`、已激活的 `VIRTUAL_ENV`、仓库 `.venv`、模块
本地 `.venv`；不会从 PATH 盲选系统 Python。

`jsonschema` 是模块的 Schema 校验依赖；紧随其后的 `requirements.txt` 安装命令会安装该依赖。

## 输入与运行

正式任务由 BambooWorkbench 主框架创建符合 JobRequest Schema 的绝对路径
`job.json`，然后调用：

```powershell
modules\moisture\run_module.bat version
modules\moisture\run_module.bat self-check
modules\moisture\run_module.bat run --job C:\absolute\path\to\job.json
```

`run --job` 支持单文件和批次。输入为 `.xlsx`；模块不会修改输入文件。进度以
JSON Lines 写入 stdout，普通诊断写入 stderr。任务输出目录中包含：

- `result.json`：最后原子写入的机器结果；
- `moisture_summary.xlsx`：五表汇总工作簿；
- `analysis_report.md`：供人工复核的分析报告。

损坏文件只影响自身；批次可以返回 `partial_success`。重复内容按文件内容指纹跳过。

## 通过主框架 GUI 测试正式模块

普通启动命令 `.\.venv\Scripts\python.exe -m app` 默认使用 `mock_modules`，
不会调用本目录中的正式水分模块。开发测试时，请从 BambooWorkbench 仓库根目录运行：

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; from app.__main__ import main; raise SystemExit(main(data_root=Path.cwd(), use_mocks=False))"
```

该命令让主框架以仓库根目录作为本地测试数据根目录，并按真实调用链执行：

```text
Registry 扫描 modules/moisture
→ Runner 启动 modules/moisture/run_module.bat
→ 模块读取主框架生成的 job.json
→ 主框架读取 result.json 和 artifacts
```

手工验收步骤：

1. 在主框架中选择 `moisture` 模块；
2. 选择一个或多个正式 `.xlsx` 文件并创建任务；
3. 历史文件若只写月日，应放在严格形如 `2026年4月份` 的目录中；
4. 等待任务完成并打开 `moisture_summary.xlsx` 和 `analysis_report.md`；
5. 检查原始 Excel 未被修改。

使用仓库根目录作为测试数据根目录时，任务文件位于
`tasks/<job_id>/output-draft/`；数据库、日志和缓存位于仓库本地的忽略目录，
不属于源码提交。成功批次应生成五张工作表，以及来料平均含水率和区间值趋势图。

当前 `0.55/0.47` 阈值仍待业务批准，因此即使统计值超过该范围，测试结果也不会
自动着色。普通启动与正式模块启动的区别是主框架配置责任，不应通过修改模块绕过。

## draft、finalize 与辅助证据

draft 可声明确定性的业务 confirmations，以及至多一个 knowledge request 和一个
需要用户同意的 AI request。模块只声明请求，不直接调用知识库或 AI。

finalize 使用 `parent_job_id` 重建 draft 根身份，重新运行完整确定性管线并严格校验
确认答案和服务响应。合法且匹配候选、规则哈希、方向、字段、观测值、置信度和证据
的结构化 AI 响应，才可把橙/绿辅助复核状态提升为红/蓝。denied、error、timeout、
缺失或非法响应均安全降级并保留确定性结果。红/蓝只表示有效辅助证据支持的高度疑似，
不是正式错误、不合格或责任结论。

## 规则、经验与阈值状态

运行时规则包与经验库均只读；正式检索只使用有效期内的 approved 经验。经验编辑工具
是离线管理端，不被 `run --job`、draft 或 finalize 引用。

当前示例阈值 `0.55`（高值）和 `0.47`（低值）保持
`pending_confirmation`，尚未获得业务批准，不是正式生产标准，也不会作为已批准规则
自动参与正式判定。生产使用前必须由业务负责人确认并通过受治理的新版本发布。

## 文档与测试

业务口径、输入样本、统计公式、颜色、AI/经验库和故障处理见 `docs/01-业务说明.md`
至 `docs/06-验收与故障处理.md`。验收 Excel 在测试运行时由脱敏参数生成，不提交客户
原始工作簿。

- 完整技术架构：`docs/07-模块完整架构.md`；
- 负责人交接、责任边界和剩余阻塞：`docs/08-负责人交接要点.md`。

```powershell
.\.venv\Scripts\python.exe -m app.tools.module_contract_cli validate modules/moisture
.\.venv\Scripts\python.exe -m pytest modules\moisture\tests -q
```

## 已知限制

- 当前仅支持计划定义的 Excel 模板语义与 1—10 个样本；
- 未批准阈值不构成生产判定标准；
- AI 和知识服务仅提供辅助证据，完全不可用时仍输出确定性结果；
- 模块不包含 Web、身份、Session、数据库、Provider、HTTP 或在线发布服务。
