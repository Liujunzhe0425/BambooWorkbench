# BambooWorkbench（竹简工作台）

面向湖南桃花江竹材科技股份有限公司的 Windows 本地品质数据工作台，由“湖南大学智创未来团队”开发。

## v1.2.0：模块治理与安全更新正式版

v1.2.0 集成三个业务模块的最新验收版本：水分模块新增历史汇总追加、经验/规则管理和任务规则快照；水煮模块完善 AI 建议与开裂复核；售后模块改为框架托管的强制 AI 接入、服务优先分析和逐文件人工复核。Windows 安装版支持启动后检查正式 Release，并在用户确认后校验、覆盖安装和自动重启。正常启动默认加载三个真实业务模块，只有显式使用 `--demo` 才加载 Mock 演示模块。

| 模块 | 版本 | 核心能力 | 主要输出 |
|---|---:|---|---|
| 竹丝水分检测 | 1.2.0 | 确定性统计、历史追加、经验/规则治理、规则快照及独立 AI 报告 | 四表汇总 Excel、异常标色、客户报告、独立 AI 报告 |
| 水煮实验 | 1.2.0 | 解析密度、膨胀率、浸渍剥离并提供经授权的 AI 建议与开裂复核 | 检测汇总、异常/冲突提示、分析报告、业务记录 |
| 售后分析 | 1.2.0 | 框架托管 AI 预分析、逐文件费用/责任工厂/投诉类型人工复核 | 全量汇总、Word 报告、年度看板及图表 |

业务口径以模块随附规则和客户确认标准为准。框架不替代品质人员的最终判断；边界、冲突和证据不足的情况进入人工确认。

## 客户使用

1. 从 [Releases](https://github.com/Liujunzhe0425/BambooWorkbench/releases) 下载 `BambooWorkbench-Setup-1.2.0.exe`。
2. 双击安装，按需勾选“创建桌面快捷方式”。
3. 打开“竹简工作台”，选择竹丝水分、水煮实验或售后分析。
4. 导入原始 Excel，完成待确认事项后等待处理完成。
5. 在结果页打开生成的 Excel 和分析报告，由有权限的人员复核最终结论。

应用无需登录，业务数据、任务历史和输出默认保存在本机。完整说明见[用户使用指南](docs/USER-GUIDE.md)，现场验收见[客户验收测试说明](docs/acceptance/CUSTOMER-UAT-GUIDE.md)。

v1.2.0 已加入安装版自动更新框架：启动后异步检查正式 Release，只有用户确认后才下载，完成 SHA-256 校验后覆盖安装并重启，失败不影响三个离线业务模块。由于当前源码仓库为私有仓库，团队测试需使用只读细粒度 GitHub Token；普通客户启用自动更新前必须配置独立的公开二进制分发源，严禁在安装包中内置或向客户分发仓库令牌。详见[自动更新设计与发布约定](docs/release/automatic-updates.md)。

## 可选 AI 配置

系统设置支持离线模式、DeepSeek 和 OpenAI 兼容接口。API 密钥只保存到 Windows 安全凭据，不写入 SQLite、任务文件或日志；每次联网发送前仍须查看脱敏预览并明确授权。

v1.2.0 中的实际能力边界：

- 竹丝水分模块的普通汇总完全确定性运行；用户可另行选择当前汇总、历史资料和已批准经验生成独立 AI 报告，AI 不修改原汇总表；
- 水煮实验模块仅在存在候选时通过统一服务请求 AI 生成原因解释和复核建议，不改变公式、阈值、等级或结构化业务记录；
- 售后分析模块进入时必须先由框架完成 Provider 配置和连接验证；每批次明确授权后，模块只生成脱敏请求并消费框架响应，费用、责任工厂、投诉类型及最终结论仍由规则和人工确认决定。

客户规则、知识库、确定性计算与人工确认的优先级始终高于模型通用知识。水分和水煮的 AI 能力可以拒绝并安全降级；售后标准任务在开始前必须完成 AI 配置和本批次授权，但任务开始后的 Provider 故障会安全降级并保留全部 Excel 处理结果。

## 本地开发与验证

要求 Python 3.12：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,packaging]"
powershell -ExecutionPolicy Bypass -File scripts\verify_repo.ps1
```

构建并验证安装包：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
powershell -ExecutionPolicy Bypass -File scripts\verify_installer.ps1
powershell -ExecutionPolicy Bypass -File scripts\prepare_release.ps1
```

模块负责人后续更新必须阅读[三个业务模块后续更新与兼容接入验收说明](docs/handoff/模块后续更新与兼容接入验收说明.md)。

水分和售后框架适配结论见[框架 FCR 适配审核记录](docs/acceptance/framework-fcr-adaptation-review-2026-07-25.md)。

## 项目信息

- 中文产品名：竹简工作台
- 英文产品名 / 仓库名：BambooWorkbench
- 对接企业：湖南桃花江竹材科技股份有限公司
- 开发团队：湖南大学智创未来团队
- 当前稳定版本：1.2.0
