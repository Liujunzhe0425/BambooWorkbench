# 竹丝水分检测模块

BambooWorkbench 竹丝水分检测模块 v0.1.0。模块通过主框架 Registry 发现，
由 Runner 经 `run_module.bat` 启动，支持确定性 Excel 分析、draft/finalize、
业务确认项以及受控的 knowledge/AI service request。模块不直接访问网络、
Provider、数据库或凭据。

## 运行方式

模块支持两种运行模式：

### 客户便携版 / 安装版（不需要 Python）

客户电脑上通过 BambooWorkbench 安装器或便携包分发的版本包含冻结的
`runtime/BambooMoistureModule.exe`，`run_module.bat` 自动发现并使用，
客户无需安装 Python 或任何依赖。

### 源码开发环境

- Windows
- Python 3.11 或更高版本（当前仓库同时在 Python 3.12 验证）

所有开发和测试命令必须显式使用当前 BambooWorkbench 仓库的虚拟环境：

```powershell
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable); print(sys.version)"
.\.venv\Scripts\python.exe -m pytest --version
.\.venv\Scripts\python.exe -m pip install -r modules\moisture\requirements.txt
```

不得使用裸 `python`、`py`、系统 Python 或全局安装的依赖。

### 启动器解释器选择顺序

`run_module.bat` 按以下优先级选择运行时：

1. `BAMBOO_MODULE_EXECUTABLE`（显式指定冻结 EXE，最高优先级）；
2. `runtime\BambooMoistureModule.exe`（随模块交付的本地冻结程序）；
3. `BAMBOO_MODULE_PYTHON`（显式指定 Python 解释器）；
4. 已激活的 `VIRTUAL_ENV`；
5. 仓库 `.venv`；
6. 模块本地 `.venv`。

启动器不会从 PATH 盲选系统 Python。冻结运行时内部包含 schemas、rules、experience、
templates 及模块 CLI 及其 Python 依赖。

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

### 快速启动

打开 PowerShell，执行：

```powershell
# 从 BambooWorkbench 仓库根目录执行
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable); print(sys.version)"
.\.venv\Scripts\python.exe -m app
```

普通启动默认发现并调用正式 `modules/moisture`；只有显式传入 `--demo`
时才使用演示模块。正式调用链为：

```text
Registry 扫描 modules/moisture
→ Runner 启动 modules/moisture/run_module.bat
→ 模块读取主框架生成的 job.json
→ 主框架读取 result.json 和 artifacts
```

### 使用自己的 Excel 测试

1. 在主框架中选择 `moisture` 模块；
2. 选择一个或多个 `.xlsx` 文件；不要选择 Excel 自动生成的 `~$` 临时文件；
3. 创建 draft 任务；若工作簿日期只有月/日，待确认页会为整批显示一个“默认业务年份”
   确认项；已有完整年月日的文件不会被该答案覆盖；
4. 输入四位业务年份并提交确认，由主框架创建 finalize 任务；
5. 在结果中心打开 `moisture_summary.xlsx` 和 `analysis_report.md`；
6. 检查汇总表、颜色和趋势图，并确认原始 Excel 未被修改。

可直接选择仓库外的业务样本目录；真实样本不得提交到 Git。

批量中存在损坏文件时，正常文件仍会处理，任务通常显示 `partial_success`。相同内容的
重复文件只计算一次。

使用仓库根目录作为测试数据根目录时，任务文件位于
`tasks/<job_id>/output-draft/` 或 `output-final/`；数据库、日志和缓存位于仓库本地的忽略目录，
不属于源码提交。成功批次应生成五张工作表，以及来料平均含水率和区间值趋势图。

`0.55/0.47` 阈值及“竹丝/原竹丝”材料范围已由负责人于 2026-07-17 批准，命中后
分别形成橙色/绿色确定性筛查提示。普通启动与演示启动的区别由主框架 `--demo` 参数控制。

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

当前阈值 `0.55`（高值）和 `0.47`（低值）处于 `confirmed`，适用于“竹丝”和
“原竹丝”，规则包版本为 `default-v1-approved`。橙/绿只表示确定性筛查疑似，
不是正式错误、不合格或责任结论；规则运行时保持只读。

## 文档与测试

业务口径、输入样本、统计公式、颜色、AI/经验库和故障处理见 `docs/01-业务说明.md`
至 `docs/06-验收与故障处理.md`。验收 Excel 在测试运行时由脱敏参数生成，不提交客户
原始工作簿。

- 完整技术架构：`docs/07-模块完整架构.md`；
- 负责人交接、责任边界和剩余阻塞：`docs/08-负责人交接要点.md`；
- 主框架正式接入、真实 AI、治理入口和报告增强要求：`框架负责人接入与功能建设要求.md`。

```powershell
.\.venv\Scripts\python.exe -m app.tools.module_contract_cli validate modules/moisture
.\.venv\Scripts\python.exe -m pytest modules\moisture\tests -q
```

## 构建便携运行时

模块提供 `build_portable_runtime.ps1`，使用仓库 `.venv` 中的 PyInstaller 以
**onedir** 方式构建 `BambooMoistureModule.exe`。该钩子由主框架构建链调用，
要求：

- 仓库 `.venv` 存在且包含 Python 3.11+ 和 PyInstaller；
- 主框架已通过 `scripts/build_portable.ps1` 生成
  `dist/BambooWorkbench/modules/moisture/` 目录及 `module.json`。

构建产物安装到：

```text
dist/BambooWorkbench/modules/moisture/runtime/
```

钩子以原子替换方式更新运行时（`.runtime.incoming` → `runtime`，失败时回滚），
只清理本模块的构建工作目录和 portable 内的 `runtime/`，不触碰其他模块、用户目录
或整个 `dist/`。每次构建后自动清理 `build/moisture-portable-runtime/`。

构建命令（由主框架 `scripts/build_real_module_runtimes.ps1` 调用）：

```powershell
powershell -ExecutionPolicy Bypass -File modules\moisture\build_portable_runtime.ps1
```

**不得提交**：`.exe`、`runtime/`、`build/`、`dist/`、`.venv` 中的任何文件。

## 已知限制

- 当前仅支持计划定义的 Excel 模板语义与 1—10 个样本；
- 当前阈值只构成筛查标准，不构成不合格或责任判定；
- AI 和知识服务仅提供辅助证据，完全不可用时仍输出确定性结果；
- 模块不包含 Web、身份、Session、数据库、Provider、HTTP 或在线发布服务。
