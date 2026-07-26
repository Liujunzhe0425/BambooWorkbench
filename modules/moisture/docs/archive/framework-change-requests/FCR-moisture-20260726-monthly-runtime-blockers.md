---
fcr_id: FCR-moisture-20260726-monthly-runtime-blockers
module_id: moisture
module_version: 1.3.0
status: completed
priority: resolved
requested_by: moisture-module-owner
target: framework
---

> 文档状态：历史归档
> 不作为当前实现和验收依据。
> 框架 PR #68（`cfc446e7`）已于 2026-07-26 解除本文两项阻塞。

# 月度运行时剩余阻塞

## 阻塞一：MonthlyRollupRunner 无法启动模块进程

水分模块完成 v1.3.0 公共 manifest、finalize 快照、rollup BAT 和 learning
适配后，真实链路：

```text
Registry → TaskService → finalize BAT → MonthlyRollupService
→ MonthlyRollupRunner → rollup BAT
```

在 `MonthlyRollupRunner` 准备离线环境时失败，rollup BAT 尚未启动。稳定错误为：

```text
'PySide6.QtCore.QProcessEnvironment' object is not iterable
```

模块直接通过以下合同运行成功：

```text
run_module.bat rollup --request <absolute-request> --response <absolute-response>
```

因此责任边界属于框架进程环境组装，不属于水分累计业务实现。

## 复现

模块测试：

```powershell
.\.venv\Scripts\python.exe -m pytest `
  modules\moisture\tests\framework\test_monthly_rollup_framework_flow.py -q
```

失败发生于框架 `core/modules/monthly_runner.py` 的离线环境构造阶段。
当前实现尝试直接遍历 `QProcessEnvironment.systemEnvironment()` 的返回对象。

## 最小修改请求

请框架负责人使用 Qt 支持的键枚举接口读取环境变量，例如读取
`QProcessEnvironment.keys()` 后逐项复制，并继续保留现有要求：

- 删除 API Key、Authorization、Password、Secret 和 Token 类环境变量；
- `BAMBOO_OFFLINE=1`；
- HTTP/HTTPS/ALL proxy 指向不可用本机端口；
- 源码模式固定 `BAMBOO_MODULE_PYTHON`；
- 不降低 stdout、响应 Schema、路径、大小和 SHA-256 校验。

不请求修改水分模块公式、规则、统计、快照、累计渲染或报告。

## 阻塞二：非月度 finalize 被错误要求返回月度快照

水分模块同时支持普通确定性汇总、独立 `ai_report` 和月度累计。当前
`ProcessRunner` 只要看到 manifest 声明 `monthly_rollup`，就要求该模块的
每一次 finalize 都必须返回 `monthly_snapshot`。因此不产生业务月度记录的
`ai_report` finalize 会在模块已经返回合法结果后，被框架改判为失败：

```text
monthly_rollup module finalize result is missing a snapshot
```

中央 `ModuleResult.monthly_snapshot` 已定义为可选字段。请框架仅在结果实际
携带 `monthly_snapshot` 时校验并登记它；或者使用中央合同中明确批准的任务
类型/年月条件判断月度资格。以下情况不得被强制创建伪快照：

- 独立 AI 报告；
- 失败或取消的 finalize；
- 其他不产生正式月度业务记录的操作。

普通水分汇总在提供 `period_year` 和 `period_month` 后仍必须产生真实快照，
不能因本修复而放宽该路径的校验。

## 验收

1. `MonthlyRollupRunner` 能启动正式 moisture `run_module.bat rollup`；
2. 源码模式和便携模式均使用批准运行时；
3. 敏感环境变量仍不进入模块进程；
4. 月度累计进程仍为完全离线；
5. 水分测试
   `test_real_framework_finalize_snapshot_and_offline_rollup` 从严格 xfail
   转为正常通过后，模块负责人移除 xfail 标记；
6. 框架原有 `tests/unit/modules/test_monthly_runner.py` 和相关仓库门禁通过。
7. 独立 `ai_report` 的允许、拒绝、超时和非法响应路径不再因缺少月度快照
   被框架改判失败；
8. 失败或取消任务不登记月度槽位，普通带年月的水分 finalize 仍登记真实快照。
