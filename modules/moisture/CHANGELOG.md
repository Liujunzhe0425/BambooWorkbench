# Changelog

## 0.1.0

### 第三轮整改 — 独立便携运行时（进行中）

- 新增 `build_portable_runtime.ps1`：使用仓库 `.venv` 中 PyInstaller onedir 构建
  `BambooMoistureModule.exe`，包含 schemas、rules、experience、templates 及 CLI 依赖。
- `run_module.bat` 新增 `BAMBOO_MODULE_EXECUTABLE` 最高优先级，并自动发现
  `runtime\BambooMoistureModule.exe`（随模块交付的本地冻结程序）。
- `runtime_paths.py` 支持 frozen 模式：`sys.frozen` 时从 `sys._MEIPASS` 解析资产根目录。
- 构建钩子实施仓库边界检查（Assert-RepositoryPath）、安全删除（Remove-SafeTree）
  和原子替换（`.runtime.incoming` / `.runtime.previous`），失败时回滚。
- 新增便携运行时构建边界测试 `test_portable_runtime_build.py`（34 项）。
- BAT 继续禁止裸 `python`、`py` 和系统 Python 回退；源码开发模式不退化。

> 真实 portable 构建验证和无 Python 环境 draft/finalize 闭环待 Codex 在 R3-C3 执行。
> 以上为已实施的代码变更，不声称 portable 端到端验收已通过。

### 初始版本

- 新增 BambooWorkbench 模块合同、`version`、`self-check` 与 `run --job`。
- 迁移已验证的水分公式、统计、Excel 解析、规则评估、经验检索和报告生成语义。
- 新增确定性批处理、去重、失败隔离、XLSX/Markdown/result 原子输出。
- 新增 draft confirmations、受限 knowledge/AI service requests 与 finalize 重放。
- 新增严格服务响应校验、离线降级和红蓝辅助证据状态。
- 新增只读运行时经验库及隔离的离线经验治理工具。
- 冻结脱敏验收场景、业务文档、安全测试和主框架真实调用证据。
- `0.55/0.47` 阈值及“竹丝/原竹丝”范围经负责人批准，作为确定性筛查规则执行。
- 正式模块成为桌面端默认发现目标，并加入 portable 构建、CI 和仓库门禁。
- 运行时只读经验引用、Knowledge 报告引用、独立 finalize 身份和聚合错误提示完成接线。
- AI 请求身份绑定 draft root job 与规则快照，年份确认后仍可严格识别框架按 draft ID 返回的 `ok`、`denied` 和 `error` 响应。
