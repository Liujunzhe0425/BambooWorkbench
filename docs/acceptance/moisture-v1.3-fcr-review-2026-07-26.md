# 水分 v1.3 月度累计与学习 FCR 审核结论

日期：2026-07-26

审核对象：`FCR-moisture-20260726-monthly-rollup-learning.md`

来源：Draft PR #65，`module/moisture-test@e7e46a92e961eb029a3a1d2d6721a320297b60b9`

框架实施：Draft PR #64，`agent/v1.3.0-framework`

## 结论

请求合理，批准采用“统一中央信封 + 水分模块薄适配”方案。

FCR 对月度槽位、不可变快照、授权快照根、完全离线累计、全部后续月份重算、一次提交、内部工件隐藏和学习证据生效条件的判断符合已批准设计，也保持了框架与模块责任边界。

框架不会直接采用水分私有类或把水分字段变成中央业务模型。模块私有 `target_period`、`business_config`、`artifacts`、`display_text` 等字段由水分 BAT/CLI 适配层映射到中央合同。

## 框架批准的最终公开入口

### Manifest

```json
{
  "capabilities": ["monthly_rollup"],
  "monthly_rollup": {
    "schema_version": "1.0",
    "entrypoint": "run_module.bat",
    "snapshot_schema": "schemas/moisture-monthly-snapshot.schema.json",
    "request_schema": "schemas/moisture-monthly-rollup-public-request.schema.json",
    "response_schema": "schemas/moisture-monthly-rollup-public-response.schema.json",
    "learning_schema": "schemas/moisture-learning-public.schema.json"
  }
}
```

字段名固定为 `monthly_rollup`，不是 FCR 建议稿中的 `monthly_rollup_contract`。`learning_schema` 仅在模块产生学习描述时声明。

### Finalize 快照

使用中央 `ModuleResult.monthly_snapshot`，不把快照混入客户可见 `outputs`：

```json
{
  "schema_version": "1.0",
  "path": "<output-final 内绝对路径>",
  "snapshot_format": "moisture-v1",
  "year": 2026,
  "month": 3
}
```

### 累计命令

```text
run_module.bat rollup --request <absolute-request.json> --response <absolute-response.json>
```

中央请求和响应以仓库生成的以下文件为唯一依据：

- `contracts/schemas/monthly-rollup-request.schema.json`
- `contracts/schemas/monthly-rollup-result.schema.json`

框架为每次目标月建立独占 `snapshot_root`，复制并复验授权快照。模块不得读取其它任务目录。

响应必须声明 `used_months`、带 `snapshot_id/month/sha256` 的 `snapshot_hashes`、`record_count`、`network_call_count=0`，以及每个输出的 `sha256`。框架会重新计算全部输出哈希。

失败响应使用中央 `error: {code, message}`。stdout 只允许公共 `ProgressEvent` JSON 行。

### Learning

中央对象字段固定为：

```text
schema_version
learning_key
field
context
context_levels
candidates [{candidate_id, label}]
base_suggestion_id
preference_adjustable
```

水分私有 `display_text` 映射到中央 `label`，`base_suggestion` 映射到 `base_suggestion_id`。中央要求基础建议必须属于候选集合，因此水分私有 `null` 在公开适配层中应回退为本次模块基础建议候选；不能凭空新增候选。

## 框架本轮补充

在 PR #64 已有月度事务和 UI 基础上，本轮补充：

1. manifest 可选 `learning_schema` 发现和安全校验；
2. 每次累计独占、只读的授权 `snapshot_root`；
3. 显式 `--response` 路径；
4. stdout JSON 进度解析和路径泄漏拒绝；
5. 成果 SHA-256 复算、使用月份和快照确认校验；
6. `network_call_count=0`；
7. 稳定失败响应外壳。

## 水分负责人下一步

1. 同步 PR #64 最新提交或至少对照上述中央 Schema。
2. 保留现有私有业务内核，新增薄适配层，不重写累计算法。
3. 增加三份 public Schema；私有 Schema可继续保留，但 manifest 只能指向 public Schema。
4. `module.json` 声明最终 `monthly_rollup` 对象和 capability。
5. finalize 把私有月度快照映射到 `ModuleResult.monthly_snapshot`。
6. BAT 支持 `rollup --request --response`，输出中央进度/响应，不输出 traceback 或绝对路径。
7. 把 supplier/department 私有学习描述映射到中央 `LearningDescriptor`，并用 public learning Schema 限制只允许这两类。
8. 增加 Registry → TaskService → Runner → BAT 的源码和便携入口测试。
9. 更新原 Draft PR #65，继续指向 `integration`，不要修改框架目录。

交付时提供最新 SHA、模块版本、完整测试、中央合同测试、月份缺口、早期替换、输出哈希错误、非法 stdout、失败外壳和零联网结果。

## 不批准的做法

- 框架直接 import `moisture.application.*`；
- 框架解释快照 payload、公式、阈值或累计业务字段；
- 模块自行维护正式月份槽位或学习数据库；
- manifest 仅靠 capability 和约定文件名推断 Schema；
- 把内部快照放进普通客户成果列表；
- 失败时回退 Mock、旧非累计输出或 AI 结果。
