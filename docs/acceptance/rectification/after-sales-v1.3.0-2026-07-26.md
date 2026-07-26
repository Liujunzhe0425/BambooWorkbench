# 售后模块 v1.3.0 整改与重新交付说明

有效交付：Draft PR #67，`module/after-sales → integration`，已验收 SHA `8daeadfdb9e0598f480149385f2c5a361e49773b`。错误指向 main 的 PR #66 已关闭。

## 当前问题

1. 分支没有同步最新 `integration@cfc446e7`。
2. manifest 只有 `monthly_rollup` capability，没有中央合同对象，静态验证失败。
3. JobRequest 解析器拒绝 `task_name / period_year / period_month / learning_enabled`。
4. 累计请求/响应仍使用 FCR 草案字段，与中央 Runner 不兼容。
5. finalize 生成模块旁路快照和 learning 文件，没有映射中央顶层字段。

本地结果：51 passed、1 failed；失败是正式 TaskService 链路拒绝中央 JobRequest 新字段。

## 位置和原因

- `module.json`：缺少完整 `monthly_rollup` 对象；没有 public learning Schema 声明。
- `src/after_sales_agent/cli.py`：JobRequest 白名单仍是旧版。
- `schemas/monthly-rollup-*.schema.json`：使用 `request_id / staging_output_dir / errors[]`，快照确认缺少 `snapshot_id`，请求缺少中央授权字段。
- `monthly_rollup.py`：可能生成多个月份快照和旁路文件，未映射单个任务目标年月的中央 `monthly_snapshot`。

## 责任边界

售后负责人负责三项人工最终值、快照 payload、累计台账、Excel、Word 和图表；框架只负责统一合同、AI Provider、月度事务、路径和学习证据。

## 整改需求和目标

1. 同步 `integration@cfc446e7` 并接受中央 JobRequest 新字段。
2. manifest 声明完整 monthly contract；提供中央 request/response/learning public Schema。
3. 薄适配中央 `transaction_id / snapshot_root / output_dir / configuration_identity / offline_required` 和稳定响应。
4. 响应提供 snapshot ID/月/SHA、record_count、成果 SHA、零联网和 `error {code,message}`。
5. 每个任务只按目标年月返回顶层 `ModuleResult.monthly_snapshot`；内部快照不进入普通 outputs。
6. 投诉类型等学习描述映射到公共 `ConfirmationPrompt.learning`，不得只写 `after_sales_learning_descriptors.json`。
7. 保持已批准的售后 AI 行为：已验证的全局配置跳过设置页，但每个售后任务仍单独询问一次联网；finalize/rollup 不重复联网。

## 验收标准

- 中央合同 CLI 退出 0；
- Registry → TaskService → Runner → BAT 完整通过；
- 服务优先 AI 只调用一次，人工确认后 finalize 复用响应；
- 月度快照只含最终人工费用、责任工厂、投诉类型及脱敏字段；
- 缺月、替换、跨年、乱序、重复、路径、输入/输出哈希、稳定错误和零联网覆盖；
- Excel、Word、图表、结构化记录在源码和便携环境可打开；
- 完整模块测试、Ruff、version/self-check、`git diff --check` 通过。

## 修改范围和禁止事项

仅修改 `modules/after_sales/`。不得再创建指向 main 的 PR，不得修改框架或其他模块，不得内置/读取 API Key，不得把旁路快照和学习文件当普通成果，不得改变业务口径后不说明。

## 重新交付

只更新 Draft PR #67，目标保持 integration。提供最新 SHA、1.3.0 版本、完整测试、合同/便携/AI 调用次数/零联网证据和重点复验接口。

## 给负责人的通知

售后业务累计内核可保留，但公开合同尚未适配，且旧 JobRequest 会拒绝 v1.3 字段。请同步 `integration@cfc446e7`，完成中央 manifest、request/response、顶层 monthly_snapshot 和公共 learning 薄适配，只更新 Draft PR #67。错误 PR #66 已关闭。

## 给 AI Agent 的执行提示词

严格只修改 `modules/after_sales/`。同步 `integration@cfc446e7`，以中央月度 Schema 为唯一公开合同；保留业务累计内核，通过薄适配替换 request_id/staging_output_dir/errors[] 等草案字段。接受中央 JobRequest 新字段，将单月快照和投诉类型学习映射到顶层 monthly_snapshot/ConfirmationPrompt.learning，保持售后逐任务联网询问和 finalize/rollup 零重复联网。完成完整合同、TaskService、便携与安全测试后只更新 Draft PR #67，并报告 SHA、版本和结果。

