# Changelog

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
