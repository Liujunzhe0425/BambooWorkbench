> 文档状态：历史归档
> 不作为当前实现和验收依据。
> 当前有效说明以 README 和三份主指导文档为准。

---
request_id: FCR-moisture-20260724-public-management-contract
module_id: moisture
target_module_version: 1.1.1
owner: moisture 模块负责人
status: module_implemented_framework_review_required
framework_areas:
  - registry
  - management
  - runner
  - task_service
  - ui
breaking_change: false
required_before_module_merge: true
pull_request: 52
---

# 框架适配请求：水分模块统一公开管理进程合同

## 1. 请求结论

本文件是水分模块经验管理、规则管理和规则快照的唯一公开合同提案。

模块 v1.1.1 已按本提案提供版本化 Schema、真实 `run_management.bat manage`
分发、能力声明和进程测试；这些属于待框架复验的模块公开合同，不能描述为中央
ManagementService 已经批准或已接入。框架批准并实现发现、前后置校验和 UI/TaskService
调用以前：

- 中央管理 Runner 仍只能使用既有 v1.0 四操作；
- GUI 不得宣称经验管理、规则管理或规则快照已经可用；
- TaskService 不得绕过进程合同直接 import 模块内部 repository/service；
- 本请求继续是 PR #52 的合并前置复验项。

现有历史汇总追加能力和 `supports_incremental: true` 不属于本次重做范围。

## 2. 当前阻塞

当前中央 `ModuleManagementRequest/Response` Schema 只支持：

```text
list_approved_experiences
import_history_summary
list_history_summaries
retire_history_summary
```

请求模型只有 `data_dir`、`input_file` 和 `history_id` 等旧字段，并使用
`additionalProperties: false`。它无法承载经验文档、规则包、版本、expected hash、
预览历史选择和规则快照身份。

模块目录中的：

```text
schemas/experience-management-request.schema.json
schemas/experience-management-response.schema.json
```

是模块 v1.1.1 的公开进程合同资产，已由模块入口自校验；中央 manifest/Runner 对其
发现和校验仍待框架实现。

## 3. 唯一实施方案

框架增加“模块自有、版本化管理合同”的发现和校验能力，仍复用现有管理进程入口，
不得直接 import 模块 Python 内部类。

目标 `module.json` 在框架支持扩展 manifest 字段后增加：

```json
{
  "management_entrypoint": "run_management.bat",
  "management_contract": {
    "schema_version": "1.1",
    "request_schema": "schemas/moisture-management-request.schema.json",
    "response_schema": "schemas/moisture-management-response.schema.json"
  }
}
```

约束：

1. Schema 路径必须是模块目录内的相对路径；
2. Registry 必须拒绝绝对路径、`..`、目录越界和不存在的 Schema；
3. 框架在启动进程前校验请求，在读取响应后校验响应；
4. 模块 CLI 使用同一份 Schema 再次校验；
5. Runner 只执行 manifest 中的 `management_entrypoint`；
6. UI、TaskService 和 Runner 不得 import 水分模块 repository/service；
7. `data_dir` 由框架授权并使用绝对路径传入；
8. 正式 `run_module.bat` 不暴露管理写操作。

模块 v1.1.1 已声明、框架需复验的 capabilities 固定为：

```json
[
  "ai_report",
  "experience_management",
  "rule_management",
  "rule_snapshot"
]
```

历史追加继续由 `supports_incremental: true` 表达，不增加重复 capability。

## 4. 进程入口

公开调用保持：

```text
run_management.bat manage --request <absolute-request.json> --response <absolute-response.json>
```

要求：

- request 和 response 必须是不同的绝对路径；
- response 必须写入框架授权任务目录；
- stdout 每行只能是进度 JSON；
- 普通诊断只能进入 stderr；
- 响应使用同目录临时文件和 `os.replace` 原子发布；
- 预期业务失败写出合法 `status=error` 响应；
- 请求合同无效退出码为 `2`；
- 响应无法原子写入退出码为 `3`；
- 未捕获内部错误退出码为 `4`，stderr 仍不得输出 traceback 或绝对路径；
- 成功和已经转换为结构化业务错误的请求退出码为 `0`。

## 5. 统一请求外壳

Schema：

```text
schemas/moisture-management-request.schema.json
```

请求结构：

```json
{
  "schema_version": "1.1",
  "request_id": "request-001",
  "module_id": "moisture",
  "operation": "get_active_rule_identity",
  "data_dir": "框架授权的绝对模块数据目录",
  "parameters": {}
}
```

公共字段：

| 字段 | 约束 |
| --- | --- |
| `schema_version` | 固定为 `1.1` |
| `request_id` | `^[A-Za-z0-9-]{6,64}$` |
| `module_id` | 固定为 `moisture` |
| `operation` | 只能是第 7 节列出的操作 |
| `data_dir` | 非空绝对路径，由框架授权 |
| `parameters` | 必须存在；按 operation 严格校验，禁止多余字段 |

`parameters` 不允许出现：

- API Key、Authorization Header 或 Provider 配置；
- 任意代码、自由公式或可执行命令；
- repository 内部路径；
- 客户身份或未经脱敏的原始行；
- UI 状态、Session、Cookie 或用户角色。

## 6. 统一响应外壳

Schema：

```text
schemas/moisture-management-response.schema.json
```

成功响应：

```json
{
  "schema_version": "1.1",
  "request_id": "request-001",
  "module_id": "moisture",
  "operation": "get_active_rule_identity",
  "status": "ok",
  "result": {
    "active_rule": {
      "version": "rules-001",
      "sha256": "64位小写SHA-256"
    }
  }
}
```

错误响应：

```json
{
  "schema_version": "1.1",
  "request_id": "request-001",
  "module_id": "moisture",
  "operation": "publish_rule",
  "status": "error",
  "error_code": "RULE_HASH_CONFLICT",
  "message": "规则已变化，请刷新后重试"
}
```

响应约束：

- `status=ok` 时必须有且只有对应操作规定的 `result`；
- `status=error` 时必须有 `error_code` 和 `message`，不得有 `result`；
- `message` 最长 300 个 Unicode 字符；
- 不得包含异常类型、traceback、绝对路径、临时文件名或原文片段；
- 所有 SHA-256 均为 64 位小写十六进制；
- 列表使用稳定 ID 升序、版本降序；
- 列表最大 500 项，历史资料列表最大 1000 项。

## 7. 完整公开操作

### 7.1 既有历史资料和 AI 经验选择

| operation | parameters | result |
| --- | --- | --- |
| `list_approved_experiences` | `{}` | `experience_items`；保持现有 AI 选择摘要语义 |
| `import_history_summary` | `input_file` | `imported_history_id` |
| `list_history_summaries` | `{}` | `history_items` |
| `retire_history_summary` | `history_id` | `history_item` |

`input_file` 必须是框架已经授权或快照的绝对 `.xlsx` 路径。模块只读输入，
不得修改或覆盖源文件。

### 7.2 经验管理

| operation | parameters | result |
| --- | --- | --- |
| `list_experience_drafts` | `{}` | `experience_items` |
| `list_experience_approved` | `{}` | `experience_items` |
| `list_experience_history` | `{}` | `experience_items` |
| `show_experience` | `experience_id`, `version` | `experience` |
| `validate_experience_draft` | `document` | `experience` |
| `create_experience_draft` | `document` | `experience` |
| `update_experience_draft` | `experience_id`, `version`, `expected_hash`, `document` | `experience` |
| `publish_experience` | `experience_id`, `version`, `expected_hash` | `experience` |
| `retire_experience` | `experience_id`, `version`, `expected_hash` | `experience` |
| `copy_experience_history_to_draft` | `experience_id`, `version`, `expected_hash`, `new_version` | `experience` |

字段约束：

- `experience_id`：`^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`；
- `version`、`new_version`：SemVer；
- `expected_hash`：64 位小写 SHA-256；
- `document`：完整 UTF-8 Markdown，1 至 65,536 字节；
- create 只接受 `status=draft`；
- update 只能修改 draft，且不得改变 ID、版本或状态；
- publish 只能发布 draft；
- retire 只能停用 approved；
- retired 不物理删除；
- 历史复制必须生成用户指定的新版本 draft，不得原地恢复 retired；
- 正式运行时只查询有效 approved 经验。

`experience_items` 每项只包含：

```text
experience_id
version
status
title
source
sha256
effective_at
applicable_suppliers
applicable_materials
applicable_seasons
applicable_metrics
supersedes
```

`experience` 只包含：

```text
experience_id
version
status
sha256
document
```

不得返回 repository 路径。

### 7.3 规则管理和当前规则身份

| operation | parameters | result |
| --- | --- | --- |
| `get_active_rule_identity` | `{}` | `active_rule` |
| `list_rule_drafts` | `{}` | `rule_items` |
| `list_current_rules` | `{}` | `rule_items`，最多一项 |
| `list_rule_history` | `{}` | `rule_items` |
| `show_rule_package` | `rule_version` | `rule_package` |
| `validate_rule_draft` | `rule_version` | `rule` |
| `preview_rule_draft` | `rule_version`, `history_ids` | `rule_preview` |
| `create_rule_draft` | `manifest`, `rules_yaml` | `rule` |
| `update_rule_draft` | `rule_version`, `expected_package_hash`, `manifest`, `rules_yaml` | `rule` |
| `publish_rule` | `rule_version`, `expected_package_hash` | `rule` |
| `retire_current_rule` | `expected_rules_sha256` | `rule` |
| `restore_rule_version` | `rule_version`, `expected_rules_sha256` | `rule` |
| `copy_rule_history_to_draft` | `rule_version`, `expected_package_hash`, `new_version` | `rule` |

字段约束：

- `rule_version`、`new_version`：1 至 128 个安全字符，并继续通过现有规则包 Schema；
- `expected_package_hash`、`expected_rules_sha256`：64 位小写 SHA-256；
- `manifest`：JSON object，必须继续通过现有 `rule-package.schema.json`；
- `rules_yaml`：UTF-8 文本，必须继续通过现有规则定义 Schema 和 Evaluator 兼容校验；
- `history_ids`：1 至 20 个受管历史资料 ID，不接受任意路径；
- preview 由模块把 ID 解析为 `<data_dir>` 下的只读历史资料；
- AI 候选只允许创建 draft，不能调用 publish；
- 发布前仍要求规则包的 `customer_confirmation_status=confirmed`；
- 已发布规则不可原地修改；
- 发布、停用和恢复使用原子 active 指针；
- 发布失败必须保持旧 active 规则有效；
- 恢复不删除历史版本；
- `0.55/0.47` 继续是待业务批准值，不因接口发布自动变为生产标准。

`rule_items` 和 `rule` 只包含：

```text
rule_version
package_id
lifecycle
rules_sha256
package_hash
source
applicable_scope
confirmation_status
```

`rule_package` 在上述字段外只增加：

```text
manifest
rules_yaml
```

`rule_preview` 只包含：

```text
batch_count
matched_batch_count
decision_count
pending_match_count
warnings
```

`active_rule` 只包含：

```text
version
sha256
```

当前没有 active 规则时，`get_active_rule_identity` 返回
`status=error, error_code=RULE_ACTIVE_NOT_FOUND`，不得静默回退 bundled 规则。

## 8. 固定错误码

公共错误：

```text
MANAGEMENT_REQUEST_INVALID
MANAGEMENT_OPERATION_UNSUPPORTED
MANAGEMENT_PATH_REJECTED
MANAGEMENT_RESPONSE_WRITE_FAILED
MANAGEMENT_DATA_CORRUPTED
```

经验错误：

```text
EXPERIENCE_NOT_FOUND
EXPERIENCE_SCHEMA_INVALID
EXPERIENCE_HASH_CONFLICT
EXPERIENCE_VERSION_CONFLICT
EXPERIENCE_STATE_CONFLICT
EXPERIENCE_PATH_REJECTED
EXPERIENCE_WRITE_FAILED
```

规则错误：

```text
RULE_NOT_FOUND
RULE_ACTIVE_NOT_FOUND
RULE_SCHEMA_INVALID
RULE_HASH_CONFLICT
RULE_VERSION_CONFLICT
RULE_STATE_CONFLICT
RULE_PREVIEW_INPUT_INVALID
RULE_PATH_REJECTED
RULE_WRITE_FAILED
```

历史资料旧错误保持兼容，不得改成未脱敏异常文本。
v1.0 当前统一使用的安全业务错误码为：

```text
MANAGEMENT_OPERATION_FAILED
```

v1.1 可以继续返回该码处理无法进一步分类的旧历史资料失败；新经验和规则操作必须
返回上面已经冻结的细分错误码，不得全部降级成该通用错误。

同一输入、同一状态必须稳定返回同一错误码。不得使用 expected 结果掩盖实际异常。

## 9. v1.0 迁移兼容

为了不破坏已经验收的历史资料和 AI 报告流程：

1. `run_management.bat manage` 在一个迁移版本内继续接受中央 v1.0 Schema 的四个旧操作；
2. 新操作只允许统一 v1.1 Schema；
3. 框架适配完成后，UI 和 TaskService 对水分模块统一发送 v1.1；
4. v1.0 兼容路径不得接受任何经验写操作或规则操作；
5. v1.0 是旧调用兼容，不是另一种新合同方案；
6. 移除 v1.0 兼容必须另行评审，不在 v1.1.1 中执行。

## 10. 规则任务快照

框架创建新的 moisture job 时：

1. 通过 `get_active_rule_identity` 查询 `{version, sha256}`；
2. 将其写入模块私有配置 `rule_selection`；
3. draft 和 finalize 都携带同一 `rule_selection`；
4. finalize 不重新查询当前 active；
5. 新规则发布只影响之后创建的新任务；
6. 指定版本缺失、损坏或 hash 不符时任务明确失败；
7. 不得静默回退其他规则或 bundled 规则。

中央 JobRequest、ModuleResult、Confirmation 和 Service Request/Response Schema 不变。
`rule_selection` 继续位于现有模块私有配置中。

## 11. 安全和运行边界

- 管理根固定在框架授权的 `<data_dir>/experience`、`<data_dir>/rules` 和历史资料目录；
- 用户字段不得直接拼接为文件路径；
- draft、published、retired 和 active 内容不得越界；
- 写入使用同目录临时文件和 `os.replace`；
- 写入失败不得破坏现有 approved 经验、active 规则或历史文件；
- 损坏 managed 目录不得静默回退 bundled 内容；
- 正式 draft/finalize 期间经验库和规则库只读；
- 不引入数据库、Web 服务、Session、身份、Provider、HTTP 或 API Key；
- 模块不直接调用 AI 或网络；
- AI 不得自动发布经验或规则。

## 12. 框架验收

框架批准并实现后，双方共同验证：

1. Registry 能读取且约束 `management_contract`；
2. Runner 经真实 `run_management.bat manage` 执行全部公开操作；
3. 请求和响应均使用同一模块 Schema 校验；
4. 路径越界、非法字段、hash 冲突、状态冲突和损坏目录返回稳定脱敏错误；
5. 原子写失败不损坏旧数据；
6. 当前规则查询只返回 `{version, sha256}`；
7. TaskService 固定规则快照，draft/finalize 身份完全一致；
8. 已验收历史追加 draft/finalize 不回归；
9. 源码与便携入口行为一致；
10. 正式 `run_module.bat` 不依赖可写管理端；
11. manifest capability 与真实可调用接口一致；
12. 模块公开版本、CLI、README 和 CHANGELOG 均为 `1.1.1`。

## 13. 回滚

框架适配未通过时：

- 不合并 PR #52；
- 不启用三项新 capability；
- 保留现有 v1.0 四操作和历史追加能力；
- 不删除模块内部 repository/service；
- 不修改已生成成果或历史任务；
- 不让 GUI 显示尚不可调用的管理入口。

## 14. 请求框架明确回复

框架复审只需对以下唯一方案给出“批准”或具体修改意见：

```text
manifest 管理合同描述符
→ 模块自有统一 v1.1 request/response Schema
→ 框架与模块双重校验
→ Runner 启动 run_management.bat manage
→ 旧 v1.0 四操作保留一个迁移版本
```

未经上述批准，模块整改停在本 FCR，不进入 Schema、CLI、capabilities 和版本升级阶段。
