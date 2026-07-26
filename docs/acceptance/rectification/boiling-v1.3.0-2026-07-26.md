# 水煮模块 v1.3.0 整改与重新交付说明

有效交付：Draft PR #63，`module/boiling → integration`，已验收 SHA `f1d55eaacc00978aef3927995858151fab7ca348`。

## 当前问题

1. 分支没有同步 PR #64/#68 后的最新 `integration@cfc446e7`。
2. manifest 声明 `monthly_rollup` capability，却没有必需的 `monthly_rollup` 合同对象，中央验证失败。
3. JobRequest 解析器拒绝 `task_name / period_year / period_month / learning_enabled`。
4. 累计请求/响应仍使用 FCR 草案字段，不兼容中央合同。
5. 月度快照和学习描述作为普通 outputs 发布，违反内部工件和公共 learning 边界。

本地结果：61 passed、2 failed、1 skipped；两项失败均为真实 TaskService 链路拒绝中央 JobRequest 新字段。

## 位置和原因

- `module.json`：缺少 `monthly_rollup {entrypoint,snapshot_schema,request_schema,response_schema,learning_schema}`。
- `src/boiling_module.py`：JobRequest 白名单和结果映射仍是旧合同。
- `schemas/monthly-rollup-*.schema.json`：使用 `request_id / candidate_snapshot / config_identity / forbid_network`，响应 error 为字符串且快照确认缺少 `snapshot_id`。
- finalize：`monthly_snapshot` 与 `confirmation_learning` 被写入普通 outputs。

## 责任边界

水煮负责人负责薄适配层、快照 payload、累计算法和成果；框架不解释水煮公式、阈值、等级或 Excel。

## 整改需求和目标

1. 同步 `integration@cfc446e7`，接受中央 JobRequest 新增字段并保持 extra-forbid。
2. manifest 声明完整中央 `monthly_rollup` 对象和 learning Schema。
3. 增加中央 request/response 薄适配，使用 `transaction_id / module_version / snapshot_root / output_dir / configuration_identity / offline_required`。
4. 响应提供 `used_months`、含 `snapshot_id/month/sha256` 的 `snapshot_hashes`、`record_count`、成果 SHA、`network_call_count=0` 和稳定 `error {code,message}`。
5. finalize 使用顶层 `ModuleResult.monthly_snapshot`，不得放入普通 outputs。
6. 把可学习确认直接映射到公共 `ConfirmationPrompt.learning`，不得只写旁路成果文件。
7. stdout 只输出公共 ProgressEvent JSON 行，诊断进入 stderr。

## 验收标准

- 中央合同 CLI 退出 0；
- Registry → TaskService → Runner → BAT 完整通过；
- 普通带年月 finalize 产出内部快照，未确认/失败/取消不产快照；
- 缺月 `[1,3]`、早月替换、跨年、乱序、重复、越界、哈希和输出哈希错误全部覆盖；
- 累计完全离线，输出不含内部快照；
- 完整模块测试、Ruff、version/self-check、源码与便携入口、`git diff --check` 通过。

## 修改范围和禁止事项

仅修改 `modules/boiling/`。不得修改中央合同或框架，不得让框架兼容草案字段，不得把快照/学习旁路文件冒充用户成果，不得改变未获业务批准的公式、阈值和等级。

## 重新交付

更新原 Draft PR #63，目标保持 integration，不新开 PR。交付最新 SHA、1.3.0 版本、完整测试、合同测试、便携测试和重点失败场景。

## 给负责人的通知

水煮业务累计内核可以保留，但公开接入尚未完成。请同步 `integration@cfc446e7`，按中央 Schema 增加 manifest 合同对象和薄适配，接受新 JobRequest 字段，并把快照/learning 从普通 outputs 移入中央字段。更新原 Draft PR #63。

## 给 AI Agent 的执行提示词

只修改 `modules/boiling/`。同步 `integration@cfc446e7` 后，以仓库中央四份 Schema 和 `docs/contracts/monthly-rollup-v1.3.md` 为唯一公开合同；保留现有业务累计内核，通过 BAT/CLI 薄适配映射中央字段。修复 JobRequest 新字段拒绝、manifest 缺失、顶层 monthly_snapshot、公共 learning、稳定错误和哈希确认。完成全链路与便携测试后只更新 Draft PR #63，报告 SHA、版本和结果。

