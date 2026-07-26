# v1.3 月度快照与年度累计公开合同

状态：框架侧已实现，模块通过 manifest 显式声明后启用
适用模块：`moisture`、`boiling`、`after_sales`

## Manifest 声明

模块必须同时在 `capabilities` 中包含 `monthly_rollup`，并提供：

```json
{
  "monthly_rollup": {
    "schema_version": "1.0",
    "entrypoint": "run_module.bat",
    "snapshot_schema": "schemas/monthly-snapshot.schema.json",
    "request_schema": "schemas/monthly-rollup-request.schema.json",
    "response_schema": "schemas/monthly-rollup-result.schema.json"
  }
}
```

三个 Schema 必须是模块目录内的真实 JSON Schema 文件。未同时声明 capability 和合同的模块不会进入累计流程。

## Finalize 快照

普通 `finalize` 的 `result.json` 增加 `monthly_snapshot`：

```json
{
  "schema_version": "1.0",
  "path": "D:/.../output-final/monthly-snapshot.json",
  "snapshot_format": "module-owned-v1",
  "year": 2026,
  "month": 3
}
```

框架校验路径包含性、年月、模块自有 Schema 后，将文件复制成任务目录中的只读不可变快照并计算大小和 SHA-256。快照必须只包含最终人工确认后的本月独立结构化记录，不得包含 API Key、Authorization Header、绝对原始输入路径或不必要的客户原文。

## 累计命令

框架调用：

```text
run_module.bat rollup --request <absolute-request-json>
```

请求遵循仓库 `contracts/schemas/monthly-rollup-request.schema.json`。快照按月份严格升序，允许月份缺口；模块必须拒绝跨模块、跨年、重复、乱序、越界、大小或哈希不一致的快照。

累计进程设置 `BAMBOO_OFFLINE=1`，移除常见敏感环境变量，并把 HTTP/HTTPS 代理指向不可用的本机端口。模块仍必须从实现上保证累计命令不调用 AI、不读取凭据、不访问网络。

模块在请求的 `output_dir` 中写入完整累计成果及 `rollup-result.json`。响应遵循 `contracts/schemas/monthly-rollup-result.schema.json`，须原样确认 transaction、模块、版本、年月和所有快照 ID/SHA-256。

## 原子提交

框架先完成候选月及全部受影响后续正式月份的累计渲染和成果校验，再统一：

1. 发布每个月的完整累计成果；
2. 切换正式月份槽位和输出映射；
3. 撤销被替换正式任务的学习贡献；
4. 激活新正式任务的学习贡献。

任一阶段失败时不切换正式槽位。已有月份的失败候选保留为 `replacement_candidate`，可在修复后重试。

## 学习描述

可学习的 `ConfirmationPrompt` 可增加 `learning`，其公共模型见 `core.contracts.result.LearningDescriptor`。上下文键不得包含姓名、地址、电话、文件、路径、客户原文等敏感概念；值必须是短小、稳定、脱敏的类别。`context_levels` 从精确到宽泛排列。框架只在当前层没有证据时才逐级回退，不混合多个层级。

每条最终答案贡献 1 个权重单位；并列时使用 `base_suggestion_id`。偏好只修改确认页建议值，永不修改模块规则、公式、阈值或跳过人工确认。

## 模块复验重点

- finalize 快照与人工最终答案一致；
- 1 月、1+2 月、1+3 月缺口和跨年隔离；
- 替换早期月份并重算所有已有后续月份；
- 累计进程无 AI/网络调用；
- 快照路径、大小、SHA-256、模块、年份和排序错误均稳定失败；
- 源码、便携运行时和安装版入口一致。
