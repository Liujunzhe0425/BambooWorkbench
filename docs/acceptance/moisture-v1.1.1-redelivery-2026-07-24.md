# 水分模块 v1.1.1 整改与重新交付说明

对象：PR #52，`module/moisture-test -> integration`，已验收提交 `a223cb1`。

## 当前问题、位置和原因

历史追加已接入且模块测试通过，但此前要求的经验管理、规则管理和任务规则快照仍停留在
模块内部 service/repository 或模块自有 Schema，未成为框架可调用的进程合同：

- `modules/moisture/module.json` 的 `capabilities` 仍只有 `ai_report`；
- `modules/moisture/src/moisture/contract/management.py` 的 `OPERATIONS` 仍只有四项旧操作；
- `run_management.bat manage` 仍只执行旧 `execute_management()`；
- 缺少当前有效规则 `{version, sha256}` 的公开只读操作；
- 模块版本仍为 `1.1.0`。

模块负责人负责公开模块合同与业务实现；框架负责人不得直接 import 水分内部 Python 类，
也不替模块决定规则阈值是否为正式生产标准。

## 整改需求和必须达到的目标

1. 保留 `supports_incremental: true` 及现有历史追加链路。
2. 选择并实现一种可由 `run_management.bat manage` 调用的稳定模块公开合同；经验和规则操作
   均必须进入实际 CLI 分发，不得只存在于内部 service。
3. 在 manifest 声明与已接线合同一致的稳定能力名：经验管理、规则管理、规则快照。
4. 提供当前有效规则只读操作，成功响应至少包含严格校验的 `version` 和小写 64 位
   `sha256`。
5. 经验三栏至少完成列出、查看、校验、创建/更新草稿、发布、停用、历史复制；规则三栏
   至少完成列出、查看、校验/预览、创建/更新草稿、发布、停用/恢复、历史复制。
6. 路径越界、非法字段、hash 冲突、状态冲突、损坏数据目录和原子写失败必须返回脱敏、
   稳定错误，不泄漏路径或 traceback。
7. 把 `module_version`、CLI version、README/CHANGELOG 统一更新为 `1.1.1`。

若认为中央 management Schema 锁定导致无法完成，不得把 FCR 标为“非合并前置”后绕过；
应在 PR #52 明确提出唯一的合同方案，等待框架复审后再实现。该选择会影响公共接口，模块
负责人不得自行把内部 Schema 当成已经获批的框架合同。

## 验收标准与自测

- Registry -> TaskService -> Runner -> `run_module.bat` 的历史追加 draft/finalize 通过；
- Runner -> `run_management.bat manage` 的全部公开经验/规则操作通过进程级测试；
- 当前规则身份查询、任务快照、draft/finalize 固定同一 hash 通过；
- Schema、路径、hash 冲突、损坏目录、错误降级和便携入口测试通过；
- 水分完整 pytest、Ruff、静态合同、version、self-check、`git diff --check` 全部通过；
- 修改范围仅限 `modules/moisture/`，不提交密钥、客户文件、真实路径、缓存或运行产物。

## 重新交付步骤与禁止事项

同步最新 `integration`，只更新原分支 `module/moisture-test` 和原 Draft PR #52；不得创建指向
`main` 的 PR，不得直接修改 `integration`/`main`，不得把测试阈值描述为获批生产标准，
不得让 AI 自动发布规则。完成后提供 PR 链接、最新 SHA、版本 `1.1.1`、改动摘要、完整测试
结果和需要重点复验的操作列表。

## 给水分负责人的人类通知

你的最新提交 `a223cb1` 已成功推送，522 项测试通过，历史追加能力已满足框架要求；但经验/
规则管理仍未进入 `run_management.bat manage` 的公开合同，manifest 也未声明对应能力，规则
身份查询缺失，因此 PR #52 暂不能合并。请按本文最小补交并统一版本为 1.1.1，继续更新原
Draft PR，不要新建指向 main 的 PR。

## 给水分负责人 AI Agent 的执行提示词

```text
在 BambooWorkbench 的 module/moisture-test 分支上整改 PR #52。先同步最新 integration，
修改范围严格限定 modules/moisture/。不要重写已通过的历史追加实现。把经验管理、规则管理、
规则快照作为真实公开进程合同接入 run_management.bat manage，更新 OPERATIONS/Schema/CLI
分发与 manifest capabilities，并提供返回 {version, sha256} 的当前规则只读操作。补齐进程级、
路径、hash 冲突、损坏目录、错误降级和 draft/finalize 快照测试。统一模块版本为 1.1.1。
运行完整 pytest、Ruff、合同、version、self-check、git diff --check。只更新原 Draft PR #52，
不得修改框架目录、integration 或 main，不得提交密钥、客户数据、真实路径、缓存或运行产物。
完成后报告 PR、完整 SHA、版本、改动、测试结果及重点复验接口。
```
