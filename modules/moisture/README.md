# 竹丝水分检测模块

BambooWorkbench 竹丝水分检测模块 v0.1.2。模块通过主框架 Registry 发现，
由 Runner 经 `run_module.bat` 启动，支持确定性 Excel 分析、draft/finalize、
业务确认项以及受控的 knowledge/AI service request。模块不直接访问网络、
Provider、数据库或凭据。

## 运行方式

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

`jsonschema` 是模块的 Schema 校验依赖；紧随其后的 `requirements.txt` 安装命令会安装该依赖。

不得使用裸 `python`、`py`、系统 Python 或全局安装的依赖。

### BAT 启动器运行时选择顺序

`run_module.bat` 按以下优先级选择运行时：

1. `BAMBOO_MODULE_EXECUTABLE`（显式指定冻结 EXE，最高优先级）；
2. `runtime\BambooMoistureModule.exe`（随模块交付的本地冻结程序）；
3. `BAMBOO_MODULE_PYTHON`（显式指定 Python 解释器）；
4. 已激活的 `VIRTUAL_ENV`；
5. 仓库 `.venv`；
6. 模块本地 `.venv`。

启动器不会从 PATH 盲选系统 Python。

## 输入与输出

正式任务由 BambooWorkbench 主框架创建符合 JobRequest Schema 的绝对路径
`job.json`，然后调用：

```powershell
modules\moisture\run_module.bat version
modules\moisture\run_module.bat self-check
modules\moisture\run_module.bat run --job C:\absolute\path\to\job.json
```

`run --job` 支持单文件（`.xlsx`）和批次。模块不会修改输入文件。进度以
JSON Lines 写入 stdout，普通诊断写入 stderr。模块能够形成合同结果时会最后原子写入
`result.json`；存在可处理业务结果的 success、partial_success 或 needs_confirmation
任务还会生成 XLSX 和 Markdown：

- `result.json`：最后原子写入的机器结果；
- `moisture_summary.xlsx`：五表汇总工作簿，按检测日期升序排列——
  - **竹丝含水率统计**（19列）：序号、供应商、材料类型、到货日期、检测日期、样本1—10、最大值、最小值、区间值、均值。命中规则的目标数值单元格直接染色（橙/绿/红/蓝），无"筛查结果"文字列；
  - **异常分析明细**（8列）：批次编号、供应商、检测日期、目标字段、观测值、筛查结果、原因、复核建议；
  - **趋势分析**（14列）：统计指标、初筛上下限和趋势图表；
  - **来源追溯**（12列）：文件、规则和样本元数据；
  - **模型分析记录**（8列）：AI复判技术字段；
  - 冻结 `F2`，筛选 `A1:S1`，日期统一 `yyyy-mm-dd`。
- `analysis_report.md`：供人工复核的分析报告。

全部输入失败时，`outputs` 可以为空，不会伪造 XLSX/Markdown。损坏文件只影响自身；
批次可以返回 `partial_success`。重复内容按文件内容 SHA-256 指纹跳过。

## 通过主框架 GUI 测试

### 快速启动

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
3. 创建 draft 任务；若工作簿日期只有月/日，待确认页会为整批显示一个"默认业务年份"
   确认项；已有完整年月日的文件不会被该答案覆盖；
4. 输入四位业务年份并提交确认，由主框架创建 finalize 任务；
5. 在结果中心打开 `moisture_summary.xlsx` 和 `analysis_report.md`；
6. 检查汇总表、颜色和趋势图，并确认原始 Excel 未被修改。

可直接选择仓库外的业务样本目录；真实样本不得提交到 Git。

批量中存在损坏文件时，正常文件仍会处理，任务通常显示 `partial_success`。相同内容的
重复文件只计算一次。任务输出位于 `tasks/<job_id>/output-draft/` 或 `output-final/`。

## 构建便携运行时

模块提供 `build_portable_runtime.ps1`，使用仓库 `.venv` 中的 PyInstaller 以
**onedir** 方式构建 `BambooMoistureModule.exe`。该钩子由主框架构建链调用，
要求：

- 仓库 `.venv` 存在且包含 Python 3.11+ 和 PyInstaller；
- 主框架已通过 `scripts/build_portable.ps1` 生成
  `dist/BambooWorkbench/modules/moisture/` 目录及 `module.json`。

构建产物安装到 `dist/BambooWorkbench/modules/moisture/runtime/`。
钩子以原子替换方式更新运行时（`.runtime.incoming` → `runtime`，失败时回滚），
只清理本模块的构建工作目录。

构建命令（由主框架 `scripts/build_real_module_runtimes.ps1` 调用）：

```powershell
powershell -ExecutionPolicy Bypass -File modules\moisture\build_portable_runtime.ps1
```

**不得提交**：`.exe`、`runtime/`、`build/`、`dist/`、`.venv` 中的任何文件。

## 常见错误

| 症状 | 可能原因 | 处理 |
|------|----------|------|
| `exit /b 4` | 没有可用 Python 3.11+ 或缺少 jsonschema | 激活仓库 `.venv` 或设置 `BAMBOO_MODULE_PYTHON` |
| `WORKBOOK_STRUCTURE_INVALID` | Excel 模板与预期不匹配 | 检查工作表名称和表头是否符合模块支持的格式 |
| `SAMPLE_LIMIT_EXCEEDED` | 工作簿超过 10 个样本 | 当前仅支持 1—10 个样本 |
| `SOURCE_FILE_MODIFIED` | 输入文件在读取期间被外部修改 | 关闭其他程序对文件的占用后重试 |
| draft 状态 `needs_confirmation` | 工作簿日期只有月/日，需确认业务年份 | 输入四位年份并提交确认 |
| 批次返回 `partial_success` | 部分文件处理失败 | 查看 `analysis_report.md` 和 stderr 了解失败文件 |

## 指导文档

详细业务规则、架构和验收标准见以下三份主指导文档：

| 文档 | 内容 |
|------|------|
| [业务规则与数据说明](docs/业务规则与数据说明.md) | 字段映射、含水率公式、统计口径、规则与阈值、颜色含义、确认边界、经验库与 AI 辅助边界、待业务批准事项 |
| [架构与开发维护指南](docs/架构与开发维护指南.md) | 目录结构、调用链、合同模型、draft/finalize 流程、经验库读写边界、测试命令、禁止修改目录和禁止依赖 |
| [验收标准与已知限制](docs/验收标准与已知限制.md) | 合同/业务/框架/安全验收、AI 降级行为、已知限制、待业务批准事项 |

下一阶段 Proposed 文档（不替代上述当前实现与验收依据）：

| 文档 | 内容 |
|------|------|
| [下一阶段架构设计](docs/architecture/moisture-next-stage-architecture.md) | 规则治理工作器、不可变规则版本、任务快照、Knowledge→AI 编排、人工复核和红蓝退出策略 |
| [框架适配请求 FCR-moisture-20260721](docs/framework-change-requests/FCR-moisture-20260721-rule-governance-runtime-analysis.md) | 请求框架提供治理进程宿主、存储、UI、active binding、服务编排、审计和打包能力 |

## 记录文件

| 文件 | 内容 |
|------|------|
| [CHANGELOG.md](CHANGELOG.md) | 版本变更历史 |
| [release-manifest.json](release-manifest.json) | 0.1.0 交付文件、构建基线和门禁结果记录 |
| [docs/framework-issues.md](docs/framework-issues.md) | 当前仍需主框架负责人处理的事项 |
| [docs/evidence/](docs/evidence/) | 已执行测试、整改和验收证据 |
| [docs/archive/](docs/archive/) | 历史计划、旧架构、迁移记录和失效方案（不作为当前实施和验收依据） |

## 常用验证命令

```powershell
.\.venv\Scripts\python.exe -m app.tools.module_contract_cli validate modules/moisture
modules\moisture\run_module.bat version
modules\moisture\run_module.bat self-check
.\.venv\Scripts\python.exe -m pytest modules\moisture\tests -q
```
