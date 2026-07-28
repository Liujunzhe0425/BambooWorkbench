# 水煮实验模块

版本：`1.3.5`　模块标识：`boiling`

## 功能

- 解析水煮实验 `.xlsx` 文件；
- 计算密度、膨胀率、浸渍剥离等业务指标；
- 对缺失信息、规则空档和需要业务判断的记录生成公共确认项；
- 输出汇总 Excel、分析报告、图表和结构化记录；
- 生成月度快照，并基于年度已有正式月份生成离线累计成果；
- 在存在候选时请求框架 AI 生成原因解释和复核建议，不改变公式、阈值或等级。

## 入口与合同

- 任务及累计入口：`run_module.bat`
- 模块清单：`module.json`
- 模块私有 Schema：`schemas/`
- 支持扩展名：`.xlsx`

```powershell
modules\boiling\run_module.bat self-check
modules\boiling\run_module.bat run --job <绝对任务文件路径>
modules\boiling\run_module.bat rollup --request <绝对请求路径> --response <绝对响应路径>
```

## 安全边界

- 核心业务计算离线、确定性运行；
- AI 只消费框架返回的结构化建议；
- 累计模式禁止联网，只读取授权的只读快照；
- 输出文件必须位于框架授权目录并提供 SHA-256；
- 不提交客户真实文件、日志、数据库或凭据。

## 业务资料

- [计算公式表](docs/计算公式表.md)
- [判定规则表](docs/判定规则表.md)
- [字段与数据来源表](docs/字段与数据来源表.md)
- [人工复核与权限边界表](docs/人工复核与权限边界表.md)
- [经验与案例表](docs/经验与案例表.md)
- [已知限制](docs/已知限制.md)

业务成果应由有权限的品质人员复核。
