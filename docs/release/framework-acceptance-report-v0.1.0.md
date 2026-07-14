# BambooWorkbench v0.1.0 框架总体验收报告

- 验收日期：2026-07-14
- 验收对象：竹简工作台 Windows 本地空框架
- 项目版本：`0.1.0`
- 测试环境：Windows 11 x64，Python 3.12.13，PyInstaller 6.21.0，Inno Setup 6.7.3
- 范围边界：不包含竹丝水分、水煮实验、售后分析的真实业务算法

## 1. 验收结论

**通过。** 当前产物已达到“可安装、可演示、可测试、可接收后续独立业务模块”的空框架目标，可进入人工创建 GitHub 私有仓库和三人并行模块开发阶段。

本结论只证明框架完整性与安全边界通过，不代表三类真实业务模块或客户质量判定已经验收。

## 2. 自动化验收证据

| 验收项 | 结果 | 证据 |
|---|---|---|
| Ruff 静态检查 | 通过 | `All checks passed!` |
| 全量源码/合同/集成/UI/打包测试 | 通过 | `305 passed, 8 skipped in 415.44s` |
| 三个模块合同样板 | 通过 | `moisture`、`boiling`、`after_sales` 合同 CLI 全部返回 0 |
| Git 差异格式 | 通过 | `git diff --check` 返回 0 |
| 便携版重新构建 | 通过 | PyInstaller 双可执行文件构建完成 |
| 便携版嵌入合同/品牌/主题/三模块 | 通过 | `verify_portable.ps1` |
| Windows 原生界面截图复核 | 通过 | 首页、历史、知识库、设置页中文字体与颜色对比正常 |
| 主程序无控制台窗口 | 通过 | PyInstaller `console=False`，PE Subsystem=`2`（Windows GUI） |
| 用户指定 Logo 与快捷方式图标 | 通过 | PNG、ICO、EXE、安装器和快捷方式图标链路完整 |
| 便携 ZIP 解压与启动 | 通过 | 隔离临时目录 `--smoke-test` 返回 0 |
| 安装包构建 | 通过 | Inno Setup 编译返回 0 |
| 安装 → 启动 → 卸载 | 通过 | 静默安装和静默卸载均返回 0 |
| 卸载保留本地用户数据 | 通过 | `%LOCALAPPDATA%\BambooWorkbench` 隔离标记文件未被删除 |
| 凭据/密钥模式扫描 | 通过 | 源码树未发现类密钥值 |
| 敏感产物与大文件扫描 | 通过 | 源码树无 Excel/数据库/密钥/日志，无超过 10 MiB 源文件 |

8 个跳过项均为 Windows 当前普通用户会话没有“创建符号链接”特权，因而无法在真实文件系统上创建测试链接。对应路径逃逸逻辑仍有不依赖该特权的单元测试覆盖；这些跳过不是功能失败。

## 3. 框架能力验收

- [x] 统一 PySide6 Windows 桌面入口，中文竹绿品牌视觉；
- [x] 深竹绿侧栏、浅色工作区、统一卡片与高对比文字，视觉基线与确认稿一致；
- [x] 无深色系统标题栏的自定义窗口栏，支持拖动、最小化、最大化和关闭；
- [x] 使用 `logo/team-logo.png` 作为界面品牌，并生成多尺寸 Windows 快捷方式图标；
- [x] 竹丝水分、水煮实验、售后分析三种模式入口；
- [x] 单文件/批量选择、输入副本与指纹，不修改原文件；
- [x] 独立模块进程、进度、超时、取消、错误隔离和恢复；
- [x] `draft` → 人工确认/公共服务 → `finalize` 闭环；
- [x] 结果、异常、输出文件和历史记录的统一展示；
- [x] 本地 SQLite、轮转日志、诊断和 Windows 用户数据目录；
- [x] 知识域、优先级检索、启用/停用和导入元数据；
- [x] 默认离线模拟 AI，以及 OpenAI 兼容 API 的隔离边界；
- [x] AI 数据脱敏预览、逐次授权、拒绝后本地继续与审计；
- [x] API 密钥仅保存到 Windows 安全凭据，不进入任务/日志/数据库；
- [x] Windows 便携版、每用户安装包、GitHub Actions 和三模块交接合同。

## 4. 最终本地产物与校验值

| 产物 | 大小 | SHA-256 |
|---|---:|---|
| `installer-output/BambooWorkbench-Setup-0.1.0.exe` | 40.59 MiB | `6A3E2C6AD29FF8DA741CB7920D47EF6CE26642958CDE1C75D1DB5C9A056F5EBF` |
| `release-output/BambooWorkbench-Portable-0.1.0.zip` | 60.59 MiB | `48AB2E0FD0A53BB74BA0A9309933DD61853882C0304A1196CB6CBCC4CB18B7C1` |
| `dist/BambooWorkbench/BambooWorkbench.exe` | 7.36 MiB | `9551812066C8A3FA67263388B23875883C7D447170B1890FB00616A850AD5F8D` |
| `dist/BambooWorkbench/BambooModuleHost.exe` | 5.30 MiB | `346FF3E8F6A508DE2C95BD1DAB856497E8908E36A52C523FC419A0DB33254535` |

安装包和便携 ZIP 为本地构建产物，已被 `.gitignore` 排除，不会随源码仓库误上传。

## 5. 已知边界

- 第一版只正式支持 Windows 10/11 x64，macOS 留作后续版本；
- 无登录系统、无多用户和无云端数据库，所有文件保存在本地；
- 当前三个是用于合同与演示的模拟模块，不能作为质量结论；
- 当前知识检索不是生产级向量检索；
- 真实 API 默认关闭，提供商配置变更后当前版本需重启生效；
- 安装包未进行商业代码签名，Windows 可能显示“未知发布者”；
- GitHub 私有仓库尚未人工创建，本验收没有进行任何远程推送。

## 6. 后续入口

- 三位组员：[`../handoff/三个业务模块最终交接说明.md`](../handoff/三个业务模块最终交接说明.md)
- 手动建仓：[`../handoff/GitHub私有仓库建仓与上传教程.md`](../handoff/GitHub私有仓库建仓与上传教程.md)
- 未来模块接收：[`../handoff/module-acceptance-checklist.md`](../handoff/module-acceptance-checklist.md)
