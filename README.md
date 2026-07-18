# BambooWorkbench（竹简工作台）

面向湖南桃花江竹材科技股份有限公司的 Windows 本地品质数据桌面框架，由“湖大智竹实践团队”开发。

## v0.1.0 的定位

这是可安装、可演示、可接收业务模块的**空框架版本**。它包含原竹丝水分检测、水煮实验和售后分析三个模拟模块，但**不包含三类业务的真实字段提取、计算公式、异常阈值、Excel 汇总和质量结论算法**。模拟输出不能用于产品放行、责任划分或赔偿决定。

## 已实现

- 一个 PySide6 桌面入口和三种模块模式；
- 参考确认稿实现的深竹绿侧栏、浅色卡片工作区、统一历史/知识库/设置页与无黑色系统栏窗口；
- 用户指定团队 Logo，以及用于主程序、安装器和快捷方式的多尺寸 Windows 图标；
- 固定 JSON 合同、模块验证 CLI 和进程故障隔离；
- 文件副本、指纹、任务进度、取消、人工确认、结果和历史；
- 本地 SQLite、日志、诊断和平台目录；
- 知识域、确定性检索、AI 脱敏预览、逐次授权和审计；
- 默认离线模拟 AI，以及隔离的 OpenAI 兼容 API 边界；
- 三个无业务规则的模拟模块；
- Windows 便携版、每用户安装包、CI、交接和演示材料。

所有用户数据默认保存在 `%LOCALAPPDATA%\BambooWorkbench`。API 密钥只通过 Windows 安全凭据保存，不进入仓库、SQLite、任务文件或日志。

## 本地开发

要求 Python 3.12：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,packaging]"
.\.venv\Scripts\python.exe -m app
```

正式启动默认只加载真实业务模块。需要演示空框架和模拟流程时，必须显式启用演示模式：

```powershell
.\.venv\Scripts\python.exe -m app --demo
```

安装版同样可使用 `BambooWorkbench.exe --demo`；Mock 输出只用于演示，不参与正式业务判断。

一键质量检查：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_repo.ps1
```

模块合同验证：

```powershell
.\.venv\Scripts\python.exe -m app.tools.module_contract_cli validate mock_modules/moisture
.\.venv\Scripts\python.exe -m app.tools.module_contract_cli validate mock_modules/boiling
.\.venv\Scripts\python.exe -m app.tools.module_contract_cli validate mock_modules/after_sales
```

## 构建 Windows 产物

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_portable.ps1
powershell -ExecutionPolicy Bypass -File scripts/build_installer.ps1
powershell -ExecutionPolicy Bypass -File scripts/verify_installer.ps1
```

便携版位于 `dist/BambooWorkbench/`，安装包位于 `installer-output/`。这些产物不会提交 Git。
最终便携 ZIP 位于 `release-output/BambooWorkbench-Portable-0.1.0.zip`。

## 模块负责人入口

- [三个业务模块最终交接说明](docs/handoff/三个业务模块最终交接说明.md)
- [模块开发与交付指南](docs/handoff/module-development-guide.md)
- [模块接收验收清单](docs/handoff/module-acceptance-checklist.md)
- [GitHub 协作流程](docs/handoff/github-workflow.md)
- [GitHub 私有仓库建仓与上传教程](docs/handoff/GitHub私有仓库建仓与上传教程.md)

框架负责人后续接收真实模块时，应先完成独立合同和业务样本验收，再将模块接入 `integration`；不得在框架核心中临时补写模块业务算法。

## 已知限制

- v0.1.0 只正式支持 Windows 10/11；
- 当前知识检索不是生产级向量检索；
- 真实 API 默认关闭，当前会话中的提供商切换需重新启动应用；
- 安装包尚未进行商业代码签名，Windows 可能显示未知发布者提示；
- macOS、登录、多用户、云数据库和真实业务模块不在本版本范围内。
