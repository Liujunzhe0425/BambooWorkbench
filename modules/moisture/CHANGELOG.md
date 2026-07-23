# Changelog

## 1.1.0 - 2026-07-23

### BambooWorkbench v1.1.0 正式发布

- 将模块清单、Python 包、运行时诊断和合同测试的当前版本统一为 `1.1.0`。
- 纳入已验收的确定性四表汇总、客户可读普通报告、独立 AI 报告、历史资料和 approved 经验选择能力。
- 本次发布同步不改变公式、阈值、颜色语义、历史四/五表兼容或人工权限边界。

## 1.0.1 - 2026-07-23

### 独立 AI 报告与四表汇总

- 普通汇总固定输出四张工作表，删除“模型分析记录”，停止普通任务中的 AI 辅助复判和红蓝提升。
- 精简普通 `analysis_report.md`：正常批次聚合计数，仅展开异常、失败、信息不足和待复核批次；
  阈值集中概括，规则哈希、内部来源及完整经验/Knowledge 引用移至技术附录。
- 新增独立 `ai_report` draft/finalize 路径：当前汇总表必选，历史资料和 approved 经验可选，合法响应生成独立 Markdown/JSON。
- 新增受控历史资料库和 `run_management.bat` 管理入口，支持四表/旧五表导入、列举、停用和 SHA-256 去重。
- 新增 approved 经验只读目录；draft、retired 或过期经验不会进入 AI 上下文。
- denied、error、timeout 和非法响应仅生成结构化降级结果，不修改原汇总表或伪造 AI 报告。
- 模块版本、manifest、合同镜像、自检和便携构建基线统一为 `1.0.1`。
- 完成真实 Registry、TaskService、Runner、Provider 编排和管理进程集成验收。

## 1.0.0 - 2026-07-22

### 正式版基线统一

- 保留 `0.1.2` 已验收的日期排序、19 列业务主表、区间值筛查和结构化 AI 辅助复核能力。
- 产品首次正式发布时，将模块运行时、清单、规则包与合同测试版本统一为 `1.0.0`；该调整不改变业务公式、阈值或输出口径。

## 0.1.2 - 2026-07-21

### 日期排序与区间值筛查

- 五张工作表按检测日期升序排列；缺失时回退到货日期；均缺失排最后；同日期按批次编号和文件哈希稳定排序。
- 主表由20列调整为19列：删除"筛查结果"文字列，业务状态通过目标数值单元格颜色直接表达。
  筛选范围由 `A1:T1` 调整为 `A1:S1`。
- 新增区间值筛查规则 `RANGE_VALUE_HIGH`：`range_value > 13%`（严格大于，等于不命中），
  命中后"区间值"单元格染橙色。区间值仅表示需复核的离散程度，不是不合格、责任或处置结论。
- 支持多命中：同一批次均值与区间值可各自命中、各自染色，不互相覆盖。
- 规则包版本更新，模块版本与合同元数据同步至 `0.1.2`。

## 0.1.1 - 2026-07-21

### XLSX 主表精简与版本一致性整改

- "竹丝含水率统计"工作表从 42 列精简为 20 列业务主表：序号、供应商、材料类型、到货日期、
  检测日期、样本1—10、最大值、最小值、区间值、均值、筛查结果。
- 技术字段重新路由：统计扩展指标 → 趋势分析（14列）、规则与文件元数据 → 来源追溯（12列）、
  AI 复判字段 → 模型分析记录（8列）、异常明细 → 异常分析明细（8列）。
- 材料类型展示层归一化为"原竹丝"（不修改源文件或 parser）。
- 筛查结果列显示四种中文文字：正常/偏高疑似/偏低疑似/需人工确认。
- 冻结 `F2`，筛选 `A1:T1`，日期统一 `yyyy-mm-dd`。
- 公式、统计、规则、AI 结果和颜色语义不变。
- 将模块清单、Python 包、构建元数据、活动规则包、运行时诊断与合同测试的版本统一为
  `0.1.1`；历史 `0.1.0` 交付记录保持不变。

## 0.1.0

### 第三轮整改 — 独立便携运行时（已完成）

- 新增 `build_portable_runtime.ps1`：使用仓库 `.venv` 中 PyInstaller onedir 构建
  `BambooMoistureModule.exe`，包含 schemas、rules、experience、templates 及 CLI 依赖。
- `run_module.bat` 新增 `BAMBOO_MODULE_EXECUTABLE` 最高优先级，并自动发现
  `runtime\BambooMoistureModule.exe`（随模块交付的本地冻结程序）。
- `runtime_paths.py` 支持 frozen 模式：`sys.frozen` 时从 `sys._MEIPASS` 解析资产根目录。
- 构建钩子实施仓库边界检查（Assert-RepositoryPath）、安全删除（Remove-SafeTree）
  和原子替换（`.runtime.incoming` / `.runtime.previous`），失败时回滚。
- 新增便携运行时构建边界测试 55 项（跨 `test_portable_runtime_build.py`、
  `test_cli_health.py`、`test_registry_runner.py`）。
- 完成真实便携构建、无 Python 环境 version/self-check 和 portable draft/finalize 闭环验证。
- 模块回归 337 passed。
- BAT 继续禁止裸 `python`、`py` 和系统 Python 回退；源码开发模式不退化。

> 验收细节见 `docs/evidence/第三轮整改验收记录.md`。

### 初始版本

- 新增 BambooWorkbench 模块合同、`version`、`self-check` 与 `run --job`。
- 迁移已验证的水分公式、统计、Excel 解析、规则评估、经验检索和报告生成语义。
- 新增确定性批处理、去重、失败隔离、XLSX/Markdown/result 原子输出。
- 新增 draft confirmations、受限 knowledge/AI service requests 与 finalize 重放。
- 新增严格服务响应校验、离线降级和红蓝辅助证据状态。
- 新增只读运行时经验库及隔离的离线经验治理工具。
- 冻结脱敏验收场景、业务文档、安全测试和主框架真实调用证据。
- `0.55/0.47` 阈值及”竹丝/原竹丝”范围从旧业务基线迁移作为默认筛查阈值，当前标注为待业务批准，仅形成橙/绿筛查提示。
- 正式模块成为桌面端默认发现目标，并加入 portable 构建、CI 和仓库门禁。
- 运行时只读经验引用、Knowledge 报告引用、独立 finalize 身份和聚合错误提示完成接线。
- AI 请求身份绑定 draft root job 与规则快照，年份确认后仍可严格识别框架按 draft ID 返回的 `ok`、`denied` 和 `error` 响应。
