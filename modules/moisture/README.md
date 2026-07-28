# 竹丝水分检测模块

版本：`1.3.5`　模块标识：`moisture`

## 功能

- 批量读取 `.xlsx` 竹丝水分检测文件；
- 生成确定性汇总表、异常筛查、分析报告和结构化业务记录；
- 支持历史标准汇总与新数据追加；
- 支持经验草稿、已批准经验、规则管理和任务规则快照；
- 生成不可变月度快照，并按年度已有正式月份生成累计成果；
- 可基于脱敏的当前汇总、历史资料和已批准经验生成独立 AI 辅助报告，AI 不修改确定性汇总。

## 入口与合同

- 任务入口：`run_module.bat`
- 管理入口：`run_management.bat`
- 模块清单：`module.json`
- 公共月度合同：`monthly_rollup` 字段声明的 Schema
- 支持扩展名：`.xlsx`

模块支持 `draft` 和 `finalize` 两阶段任务。信息缺失、日期冲突、规则冲突或需要业务判断时返回公共确认项；成功 finalize 时输出月度快照供框架登记。

## 运行

`jsonschema` 是模块的 Schema 校验依赖；紧随其后的 `requirements.txt` 安装命令会安装该依赖。

```powershell
python -m pip install -r modules\moisture\requirements.txt
```

```powershell
modules\moisture\run_module.bat self-check
modules\moisture\run_module.bat run --job <绝对任务文件路径>
modules\moisture\run_module.bat rollup --request <绝对请求路径> --response <绝对响应路径>
```

## 安全边界

- 普通汇总完全离线运行；
- 模块进程不直接持有 AI API Key；
- 输入、输出、请求、响应和快照路径必须位于框架授权目录；
- 月度累计只读取框架提供的只读快照副本；
- 学习描述只包含稳定场景标识、候选项和脱敏上下文；
- 不提交客户真实文件、日志、数据库或凭据。

## 业务资料

- [业务规则与数据说明](docs/业务规则与数据说明.md)
- [经验与规则管理使用教程](docs/经验与规则管理使用教程.md)

业务公式、阈值、颜色语义和最终结论以受控规则资产及客户确认口径为准。
