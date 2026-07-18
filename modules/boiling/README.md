# 水煮实验模块

`module_id: boiling`，版本 `0.1.0`，负责人 `anyuyu1`。

本模块读取 BambooWorkbench 任务 JSON 明确列出的 `.xlsx` 输入副本，抽取水煮实验字段，复算厚度、体积、密度、密度差与膨胀率，保留原表浸渍剥离结论，并生成结构化 `result.json`、汇总 Excel 和 Markdown 分析报告。

业务处理覆盖：

- 提取产品、规格、压制日期、班长、检测日期、浸胶日期和订单信息；
- 复核平均厚度、体积、密度、密度差和膨胀率；
- 提取浸渍剥离合格/不合格结论，支持不同工作表、试件数量、起始列和测点行数；
- 明确区分正常、异常、信息不足和待确认；
- 原表结论与规则观察冲突时保留两者并提示人工复核；
- 产品用途缺失时不选择膨胀率标准；
- 空表、未完成表或关键字段不全的文件不进入正常统计。

模块不包含独立 GUI、定时运行或目录扫描功能；不修改输入文件、不联网、不调用 AI、不创建子进程，只写任务声明的 `output_dir`。

## 安装依赖

```powershell
python -m pip install -r modules/boiling/requirements.txt
```

## 命令

```powershell
modules\boiling\run_module.bat version
modules\boiling\run_module.bat self-check
modules\boiling\run_module.bat run --job D:\absolute\path\job.json
```

## 任务阶段

- `draft`：执行解析、复算和观察；产品用途缺失或原表/复算冲突时返回人工确认项。
- `finalize`：从 `confirmation_file` 读取确认答案。产品用途仍缺失时该文件失败，不会擅自选择膨胀率标准。

客户尚未确认的密度和膨胀率阈值只触发观察项，不写成正式合格/不合格结论。具体规则和权限边界见 `docs/`。

## 输出

- `result.json`：符合 `contracts/schemas/module-result.schema.json` 的机器结果。
- `boiling_summary.xlsx`：正常汇总、未纳入正常统计清单、试件明细、规则说明和分析图表。
- `boiling_analysis.md`：便于人工复核的文字摘要。
- `boiling_records.json`：包含四类业务状态、原表值、复算值、规则观察和冲突信息的机器可读记录。

## 验证

在仓库根目录执行：

```powershell
python -m app.tools.module_contract_cli validate modules/boiling
python -m pytest modules/boiling/tests -q
powershell -ExecutionPolicy Bypass -File scripts/verify_repo.ps1
```

脱敏样例位于 `samples/input/`，对应机器预期位于 `samples/expected/`。正式交付不包含真实企业 Excel、运行日志、数据库、密钥、客户路径或接口响应。
