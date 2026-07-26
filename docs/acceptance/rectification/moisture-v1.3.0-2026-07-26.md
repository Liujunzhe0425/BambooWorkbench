# 水分模块 v1.3.0 整改与重新交付说明

有效交付：Draft PR #65，`module/moisture-test → integration`，已验收 SHA `a278ef3ef9185b511a4fb902022165439c261366`。

## 当前问题

1. 分支尚未同步框架修复后的 `integration@cfc446e7`。
2. 5 项 strict xfail 的原因和预期已过期。
3. AI report 测试仍等待旧版“每任务联网授权确认”；v1.3 已批准水分遵守系统全局默认，不再逐任务询问。
4. 历史追加测试仍假定正式累计结果只有 Excel 和 Markdown，遗漏框架发布的 `moisture_business_records.json`。
5. 交接文档存在 4 处尾随空格，`git diff --check` 失败。

## 位置和原因

- `tests/framework/test_monthly_rollup_framework_flow.py`：框架 #68 后真实累计链路已通过。
- `tests/framework/test_task_service_flow.py`：两项环境阻塞已解除；一项输出集合预期仍是旧结构。
- `tests/framework/test_ai_report_framework_flow.py`：授权交互预期与已批准全局策略不一致。
- `docs/evidence/v1.3.0-monthly-rollup-framework-handoff-2026-07-26.md`：尾随空格。

框架运行时问题已由 PR #68 解决，不再要求模块修改框架目录。

## 责任边界

水分负责人负责更新模块测试、公开适配、业务快照和累计成果；框架负责人不修改水分公式、阈值、Excel、统计口径或模块测试预期。

## 整改需求和目标

1. 合入最新 `integration@cfc446e7`。
2. 删除已经解除的月度 Runner strict xfail，并使测试正常通过。
3. 按全局默认允许/拒绝重写 AI report 测试，不再等待任务内授权确认；验证允许时调用一次、拒绝时零调用，均不生成月度快照。
4. 更新历史追加累计成果断言，包含结构化业务记录；确认内部快照仍不进入普通 outputs。
5. 清理尾随空格。
6. 保持中央 manifest、BAT、Schema 和 learning 映射不倒退。

## 验收标准

- `python -m app.tools.module_contract_cli validate modules/moisture` 退出 0；
- 月度 finalize → snapshot → offline rollup 正常通过，不再 xfail；
- AI report 的全局允许、拒绝、Provider 错误/超时/非法响应全部正常结束且不进入月度事务；
- 普通带年月 summary 仍必须产出真实快照；
- 完整模块测试无非业务待批准之外的 xfail/xpass；
- Ruff、Schema 同步、version、self-check、`git diff --check` 通过。

## 修改范围和禁止事项

仅修改 `modules/moisture/`。不得修改 `app/`、`core/`、`ui/`、`contracts/`、其他模块、`integration` 或 `main`；不得伪造快照、放宽哈希/路径校验或恢复逐任务联网确认。

## 重新交付

同步最新 integration 后更新原 Draft PR #65，不新开 PR。完成后提供最新 SHA、模块版本、完整测试统计、删除/保留的 xfail 清单、中央合同结果和重点复验命令。

## 给负责人的通知

水分公共适配主体合理，框架阻塞已通过 PR #68 合入 integration。请同步 `cfc446e7`，更新 5 项过期 xfail、AI report 全局联网策略预期、累计业务记录输出断言并清理尾随空格，然后继续更新原 Draft PR #65。

## 给 AI Agent 的执行提示词

严格在 `modules/moisture/` 内工作。先合入 `integration@cfc446e7`，读取中央月度合同和本说明；不要修改业务公式、阈值或框架。移除已解除的 Runner xfail，按水分遵守全局联网默认且任务内不再询问的规则重写 AI report 测试，更新累计业务记录成果断言，清理尾随空格。运行完整模块、中央合同、BAT version/self-check、Ruff 和 diff-check；只更新 Draft PR #65，并报告 SHA、1.3.0 版本和全部测试结果。

