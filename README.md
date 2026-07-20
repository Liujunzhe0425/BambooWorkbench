# BambooWorkbench（竹简工作台）

面向湖南桃花江竹材科技股份有限公司的 Windows 本地品质数据工作台，由“湖南大学智创未来团队”开发。

## v0.2.1：首个可复现稳定版

v0.2.1 集成三个真实业务模块，并修复 v0.2.0 发布源码与人工上传安装包不同源的问题。正常启动默认加载真实模块；只有显式使用 `--demo` 才加载 Mock 演示模块。

| 模块 | 核心能力 | 主要输出 |
|---|---|---|
| 竹丝水分检测 | 批量读取水分检测 Excel，统计并按规则标记异常 | 汇总 Excel、异常标色、分析报告、人工复核项 |
| 水煮实验 | 解析密度、膨胀率、浸渍剥离等数据并执行规则判定 | 统计摘要、异常/冲突提示、分析报告 |
| 售后分析 | 汇总售后案件，多标签分类并分析费用与解决状态 | 汇总 Excel、统计图表、分析报告、复核项 |

业务口径以模块随附规则和客户确认标准为准。框架不擅自替代品质人员的最终判断：边界、冲突和证据不足的情况进入人工确认。

## 客户使用

1. 从 [Releases](https://github.com/Liujunzhe0425/BambooWorkbench/releases) 下载最新的 `BambooWorkbench-Setup-0.2.1.exe`。
2. 双击安装，按需勾选“创建桌面快捷方式”。
3. 打开“竹简工作台”，选择竹丝水分、水煮实验或售后分析。
4. 导入原始 Excel，确认任务后等待处理完成。
5. 在结果页打开生成的 Excel、图表与分析报告；对待确认项由有权限的人员复核。

应用无需登录，业务数据、历史任务和输出默认保存在本机。完整说明见 [用户使用指南](docs/USER-GUIDE.md)，现场验收见 [客户验收测试说明](docs/acceptance/CUSTOMER-UAT-GUIDE.md)。

## 可选 AI 配置

系统设置支持三种模式：

- 离线模拟：默认不联网，不需要密钥；
- DeepSeek：默认地址 `https://api.deepseek.com`，默认模型 `deepseek-v4-flash`；
- OpenAI 兼容接口：可填写自定义接口地址和模型。

API 密钥只保存到 Windows 安全凭据，不写入 SQLite、任务文件或日志。即使启用联网，每次发送仍须先查看脱敏预览并明确确认。客户规则、知识库与人工确认的优先级始终高于模型通用知识。

## 本地开发与验证

要求 Python 3.12：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,packaging]"
powershell -ExecutionPolicy Bypass -File scripts\verify_repo.ps1
```

构建安装包：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
powershell -ExecutionPolicy Bypass -File scripts\verify_installer.ps1
```

## 项目信息

- 中文产品名：竹简工作台
- 英文产品名 / 仓库名：BambooWorkbench
- 对接企业：湖南桃花江竹材科技股份有限公司
- 开发团队：湖南大学智创未来团队
- 当前版本：0.2.1
