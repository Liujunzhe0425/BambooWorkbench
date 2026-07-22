# BambooWorkbench（竹简工作台）

面向湖南桃花江竹材科技股份有限公司的 Windows 本地品质数据工作台，由“湖南大学智创未来团队”开发。

## v1.0.0：首个正式发布版

v1.0.0 是完成框架接入、三模块联调和首轮人工验收后的首个正式版本。正常启动默认加载三个真实业务模块；只有显式使用 `--demo` 才加载 Mock 演示模块。

| 模块 | 版本 | 核心能力 | 主要输出 |
|---|---:|---|---|
| 竹丝水分检测 | 1.0.0 | 批量读取检测 Excel，统计、规则筛查和可选 AI 辅助复核 | 汇总 Excel、异常标色、分析报告、人工复核项 |
| 水煮实验 | 1.0.0 | 解析密度、膨胀率、浸渍剥离等数据并执行规则判定 | 检测汇总、异常/冲突提示、分析报告、业务记录 |
| 售后分析 | 1.0.0 | 汇总售后案件，多标签分类、费用统计和逐案人工复核 | 全量汇总 Excel、年度统计、分析报告、业务记录 |

业务口径以模块随附规则和客户确认标准为准。框架不替代品质人员的最终判断；边界、冲突和证据不足的情况进入人工确认。

## 客户使用

1. 从 [Releases](https://github.com/Liujunzhe0425/BambooWorkbench/releases) 下载 `BambooWorkbench-Setup-1.0.0.exe`。
2. 双击安装，按需勾选“创建桌面快捷方式”。
3. 打开“竹简工作台”，选择竹丝水分、水煮实验或售后分析。
4. 导入原始 Excel，完成待确认事项后等待处理完成。
5. 在结果页打开生成的 Excel 和分析报告，由有权限的人员复核最终结论。

应用无需登录，业务数据、任务历史和输出默认保存在本机。完整说明见[用户使用指南](docs/USER-GUIDE.md)，现场验收见[客户验收测试说明](docs/acceptance/CUSTOMER-UAT-GUIDE.md)。

## 可选 AI 配置

系统设置支持离线模式、DeepSeek 和 OpenAI 兼容接口。API 密钥只保存到 Windows 安全凭据，不写入 SQLite、任务文件或日志；每次联网发送前仍须查看脱敏预览并明确授权。

v1.0.0 中的实际能力边界：

- 竹丝水分模块已接入统一 AI 服务。AI 只复核确定性规则筛出的有限候选，不重新计算统计值，也不替代人工结论；
- 水煮实验模块当前使用离线确定性规则，不调用 AI；
- 售后分析桌面模块当前使用离线规则和人工复核，其独立环境中的 AI 代码尚未接入工作台统一授权协议。

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
- 当前版本：1.0.0
