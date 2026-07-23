# BambooWorkbench（竹简工作台）

面向湖南桃花江竹材科技股份有限公司的 Windows 本地品质数据工作台，由“湖南大学智创未来团队”开发。

## v1.1.0：客户首轮优化正式版

v1.1.0 完成客户首轮反馈优化并正式集成三个业务模块的最新验收版本：改进确认事项、结果阅读、失败明细、成果目录和页面导航，统一任务完成状态，并补齐水分独立 AI 报告、水煮 AI 辅助说明及售后可视化成果。正常启动默认加载三个真实业务模块，只有显式使用 `--demo` 才加载 Mock 演示模块。

| 模块 | 版本 | 核心能力 | 主要输出 |
|---|---:|---|---|
| 竹丝水分检测 | 1.1.0 | 批量读取检测 Excel，确定性统计、规则筛查和独立 AI 辅助报告 | 四表汇总 Excel、异常标色、客户报告、独立 AI 报告 |
| 水煮实验 | 1.1.0 | 解析密度、膨胀率、浸渍剥离并提供经授权的 AI 辅助说明 | 检测汇总、异常/冲突提示、分析报告、业务记录 |
| 售后分析 | 1.1.0 | 多标签案件统计、逐案人工复核、AI 辅助分析和可视化 | 全量汇总、Word/Markdown 报告、年度看板及图表 |

业务口径以模块随附规则和客户确认标准为准。框架不替代品质人员的最终判断；边界、冲突和证据不足的情况进入人工确认。

## 客户使用

1. 从 [Releases](https://github.com/Liujunzhe0425/BambooWorkbench/releases) 下载 `BambooWorkbench-Setup-1.1.0.exe`。
2. 双击安装，按需勾选“创建桌面快捷方式”。
3. 打开“竹简工作台”，选择竹丝水分、水煮实验或售后分析。
4. 导入原始 Excel，完成待确认事项后等待处理完成。
5. 在结果页打开生成的 Excel 和分析报告，由有权限的人员复核最终结论。

应用无需登录，业务数据、任务历史和输出默认保存在本机。完整说明见[用户使用指南](docs/USER-GUIDE.md)，现场验收见[客户验收测试说明](docs/acceptance/CUSTOMER-UAT-GUIDE.md)。

## 可选 AI 配置

系统设置支持离线模式、DeepSeek 和 OpenAI 兼容接口。API 密钥只保存到 Windows 安全凭据，不写入 SQLite、任务文件或日志；每次联网发送前仍须查看脱敏预览并明确授权。

v1.1.0 中的实际能力边界：

- 竹丝水分模块的普通汇总完全确定性运行；用户可另行选择当前汇总、历史资料和已批准经验生成独立 AI 报告，AI 不修改原汇总表；
- 水煮实验模块仅在存在候选时通过统一服务请求 AI 生成原因解释和复核建议，不改变公式、阈值、等级或结构化业务记录；
- 售后分析模块通过统一服务辅助问题分类、原因摘要和复核建议，费用、责任工厂、投诉类型及最终结论仍由规则和人工确认决定。

客户规则、知识库、确定性计算与人工确认的优先级始终高于模型通用知识。未配置密钥、关闭联网或拒绝某次发送，都不会阻止离线处理。

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

## 项目信息

- 中文产品名：竹简工作台
- 英文产品名 / 仓库名：BambooWorkbench
- 对接企业：湖南桃花江竹材科技股份有限公司
- 开发团队：湖南大学智创未来团队
- 当前稳定版本：1.1.0
