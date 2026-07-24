---
request_id: FCR-moisture-20260724-experience-management
module_id: moisture
module_version: 1.1.0
owner: moisture模块负责人
status: module_contract_frozen
framework_areas:
  - ui
  - management
  - storage
breaking_change: false
required_before_module_merge: false
---

# 框架适配请求：轻量经验管理

## 目标

在现有approved经验选择能力上增加轻量三栏管理：

```text
经验草稿 | 当前已批准经验 | 历史版本
```

模块侧继续复用现有Schema、SHA-256、路径防护、原子写入及
`draft → approved → retired` 生命周期。正式任务运行时保持只读。

## 最小框架改动

1. 提供独立经验管理页面和管理进程操作，不加入普通`run_module.bat`；
2. 三栏支持查看、创建/修改草稿、校验、单人确认发布、停用及历史复制为新草稿；
3. 管理进程只访问框架授权的`<data_dir>/experience`；
4. 页面只显示稳定ID、版本、状态、标题、来源、scope和hash，不显示绝对路径；
5. AI报告经验选择与管理后的同一approved目录一致。

## 固定边界

- approved/retired不可原地修改，retired不物理删除；
- draft、retired、未来生效或hash不匹配条目不得进入AI；
- 管理目录损坏时不得静默回退模块内置经验；
- AI不得发布、停用或复制经验；
- 不建设登录、角色、多级审批、数据库或网络经验库。

## 模块公开合同冻结（2026-07-24）

### 合同分层

当前`schemas/contracts/module-management-*.schema.json`是中央官方Schema的
字节镜像，并受`schema-lock.json`保护。模块不得单独扩展这些文件，框架也不得要求
模块通过修改镜像抢跑。

经验管理使用两份模块自有Schema：

```text
schemas/experience-management-request.schema.json
schemas/experience-management-response.schema.json
```

它们不加入中央`schema-lock.json`，不改变现有历史资料管理合同，也不改变
JobRequest、ModuleResult、Confirmation或Service Request/Response。

### 固定操作名

```text
list_experience_drafts
list_experience_approved
list_experience_history
show_experience
validate_experience_draft
create_experience_draft
update_experience_draft
publish_experience
retire_experience
copy_experience_history_to_draft
```

操作名冻结后不得由页面层改写或增加同义别名。

### 请求公共字段

所有请求必须包含：

```json
{
  "schema_version": "1.0",
  "request_id": "request-001",
  "module_id": "moisture",
  "operation": "list_experience_drafts",
  "data_dir": "框架授权的绝对模块数据目录"
}
```

可选业务字段只有：

```text
experience_id
version
expected_hash
document
new_version
```

字段组合固定为：

| operation | 必需业务字段 |
| --- | --- |
| 三个list操作 | 无 |
| `show_experience` | `experience_id`, `version` |
| `validate_experience_draft` | `document` |
| `create_experience_draft` | `document` |
| `update_experience_draft` | `experience_id`, `version`, `expected_hash`, `document` |
| `publish_experience` | `experience_id`, `version`, `expected_hash` |
| `retire_experience` | `experience_id`, `version`, `expected_hash` |
| `copy_experience_history_to_draft` | `experience_id`, `version`, `expected_hash`, `new_version` |

未列出的字段必须拒绝。`version`在复制操作中表示来源历史版本；
`new_version`表示新草稿版本。`document`最大为65,536 UTF-8字节。

### 标识、版本和hash

- `experience_id`沿用`experience.schema.json`的安全ID格式；
- `version`和`new_version`沿用现有SemVer格式；
- `expected_hash`必须是64位小写SHA-256；
- update、publish、retire和copy必须执行expected-hash并发检查；
- request和response不得包含绝对经验文件路径。

### 响应公共字段

所有响应必须包含：

```text
schema_version
request_id
module_id
operation
status = ok | error
```

列表操作返回`experience_items`。每个摘要只包含：

```text
experience_id, version, status, title, source, sha256, effective_at,
applicable_suppliers, applicable_materials, applicable_seasons,
applicable_metrics, supersedes
```

scope字段使用字符串数组，不使用逗号拼接字符串。

show、validate、create、update、publish、retire和copy返回单个`experience`，只包含：

```text
experience_id, version, status, sha256, document
```

`document`是完整UTF-8 Markdown（含front matter），不返回repository路径。
错误响应只返回`error_code`和不超过300字符的脱敏`message`，不得返回异常类型、
traceback、绝对路径或原文片段。

### 固定错误码

```text
MANAGEMENT_REQUEST_INVALID
EXPERIENCE_NOT_FOUND
EXPERIENCE_SCHEMA_INVALID
EXPERIENCE_HASH_CONFLICT
EXPERIENCE_VERSION_CONFLICT
EXPERIENCE_STATE_CONFLICT
EXPERIENCE_PATH_REJECTED
EXPERIENCE_WRITE_FAILED
```

预期业务失败仍以进程退出码0返回`status=error`；请求合同无效退出2；
响应无法原子写入退出3。stdout仍只能输出进度JSON。

### 生命周期与公开行为

- list只返回对应栏位，稳定按ID升序、版本降序；
- validate只校验，不写文件；
- create只允许`status=draft`；
- update只允许修改draft，且不得改变ID、版本或状态；
- publish只允许draft，生成新的approved内容和hash；
- retire只允许approved，不物理删除；
- copy只允许retired，生成指定`new_version`的draft并记录supersedes；
- approved和retired不可原地修改；
- 正式`run_module.bat`不得暴露任何写操作；
- 只有上述公开合同完整接线并通过进程测试后，manifest才声明
  `experience_management`能力。

### 当前框架阻塞

现有`ModuleManagementRequest/Response`只支持历史资料和approved经验只读列表，
不能承载上述文档、版本和hash字段。框架需要选择以下等价方式之一：

1. 提供可按模块自有Schema验证的通用管理进程宿主；或
2. 新增独立经验管理Runner，仍通过`run_management.bat`启动。

不得要求模块修改中央Schema镜像，也不得由框架直接import模块Python内部类。

## 验收

- 草稿创建/修改、hash冲突、非法Schema、路径越界和原子失败安全；
- publish后可由新的AI任务按ID/版本/hash选择；
- retire后不再可选，历史文件仍保留；
- 新发布其他经验不改变已经固定选择的AI任务；
- 正式draft/finalize依赖图不包含可写管理repository；
- 便携管理进程与源码行为一致。

## 框架方审核

- 初审结论：业务方向认可；因缺少公开合同暂缓页面接线
- 模块公开合同：已按本文件冻结，等待框架复审
- 实施分支/PR：待框架负责人填写
