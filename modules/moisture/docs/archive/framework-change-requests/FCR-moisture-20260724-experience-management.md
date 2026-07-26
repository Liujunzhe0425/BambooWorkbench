> 文档状态：历史归档
> 不作为当前实现和验收依据。
> 当前有效说明以 README 和三份主指导文档为准。

---
request_id: FCR-moisture-20260724-experience-management
module_id: moisture
module_version: 1.1.1
owner: moisture 模块负责人
status: superseded_by_unified_contract
framework_areas:
  - ui
  - management
  - storage
breaking_change: false
required_before_module_merge: true
superseded_by: FCR-moisture-20260724-public-management-contract
---

# 框架适配请求：轻量经验管理

> 本文件不再单独定义公开进程合同。
> 唯一有效的公开合同、操作名、字段、错误码、进程入口和验收要求见：
>
> `FCR-moisture-20260724-public-management-contract.md`

## 保留的业务目标

经验管理继续采用三栏：

```text
经验草稿 | 当前已批准经验 | 历史版本
```

模块继续复用现有：

- `draft → approved → retired` 生命周期；
- Schema 和 SHA-256 校验；
- expected hash 冲突检查；
- 路径保护和原子写入；
- 历史版本复制为新 draft；
- 正式任务运行时只读 approved 经验。

不建设登录、角色、多级审批、数据库、在线协作或网络经验库。AI 不得发布、
停用或恢复经验。

## 当前状态

- 内部 repository/service：已存在；
- 模块私有 Schema：仅作为设计资产，尚不是批准的框架合同；
- `run_management.bat manage`：尚未接入经验治理操作；
- manifest capability：尚未声明；
- 框架页面：尚未接入；
- 合并前置：是，必须先批准统一 FCR。

本文件不得再用于绕过统一合同复审。
