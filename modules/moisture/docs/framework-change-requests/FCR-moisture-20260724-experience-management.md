---
request_id: FCR-moisture-20260724-experience-management
module_id: moisture
module_version: 1.0.1
owner: moisture模块负责人
status: proposed
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

## 验收

- 草稿创建/修改、hash冲突、非法Schema、路径越界和原子失败安全；
- publish后可由新的AI任务按ID/版本/hash选择；
- retire后不再可选，历史文件仍保留；
- 新发布其他经验不改变已经固定选择的AI任务；
- 正式draft/finalize依赖图不包含可写管理repository；
- 便携管理进程与源码行为一致。

## 框架方审核

- 审核结论：待审核
- 实施分支/PR：待填写
