> 文档状态：历史归档
> 不作为当前实现和验收依据。
> 当前有效说明以 README 和三份主指导文档为准。

---
# 水分模块主框架接入与功能建设要求

> 接收对象：BambooWorkbench 主框架负责人、安全/AI 负责人和最终验收负责人  
> 适用基线：`modules/moisture` 0.1.0 及当前 Job、Result、Confirmation、Service Request/Response 合同  
> 实施顺序：P0 → P1 → P2 → P3；每一阶段独立实现、测试和验收

## 1. 目的与当前状态

`modules/moisture/` 已具备 Excel 只读解析、公式复核、统计、规则执行、只读经验检索、
draft/finalize、confirmation、service request/response 严格校验、XLSX/Markdown/result
输出和离线降级能力。本文件不要求主框架重新实现这些业务算法，而是明确正式接入、真实
AI、治理入口和报告增强仍需由主框架补齐的责任。

当前必须如实区分以下状态：

- 正式 moisture 模块已经存在于 `modules/moisture`，不得迁入 `mock_modules`；
- 主框架已经具备 Registry、Runner、TaskService 和服务编排基础；
- 设置页可以保存 AI 配置，但 Bootstrap 当前仍固定使用 `MockProvider`，真实 Provider 尚未打通；
- 主框架本地知识库可以检索和导入资料，但它不等于模块的版本化经验库；
- 经验库已有离线治理服务和命令，尚无主框架管理页面；
- 正式规则包运行时只读，尚无规则草稿、批准、发布和回滚页面；
- 当前 Markdown 报告以确定性模板为主，AI 报告增强尚未实现。

任何界面不得把“已保存配置”显示成“真实服务已生效”，也不得把 Mock 结果显示成真实 AI
结果。

## 2. 固定边界

1. moisture 模块负责业务计算和响应校验，主框架不得把业务公式、阈值或颜色算法复制到
   `app/`、`core/` 或 `ui/`。
2. API Key、Provider、网络访问、用户同意、凭据存储和调用审计只能由主框架负责。
3. 模块运行时只通过 `service_requests` 请求 AI 或知识服务，不得直接调用 HTTP、Provider
   或主框架数据库。
4. 正式 draft/finalize 期间，规则库和经验库必须只读；编辑和发布只能通过独立管理入口执行。
5. AI、知识和经验只能提供辅助证据或报告引用，不能替代确定性公式和已批准规则。
6. 橙/绿是确定性筛查，红/蓝是通过严格校验的辅助证据增强；所有颜色均不是正式不合格、
   责任、处罚、放行或结案结论。
7. 未经业务负责人批准的阈值、适用范围、经验和报告措辞不得作为正式版本发布。

## 3. P0：正式模块接入

### 3.1 注册和选择

- 默认 GUI 必须发现并选择 `modules/moisture`，注册结果为 `module_id=moisture`、
  `is_mock=false`。
- 生产可发现目录不得继续保留同 ID 的 moisture Mock。旧 Mock 场景应迁到
  `tests/fixtures/modules/`，只通过测试依赖注入使用。
- Registry 扫描多个来源时必须保证 `module_id` 唯一；正式模块确定性覆盖同 ID Mock，并记录
  冲突来源和最终选择。
- 正式模块缺失、manifest 非法、自检失败或启动失败时必须明确报错，禁止静默回退到 Mock。
- 其他尚未交付的 Mock 模块可以保留，但界面必须明确显示其 Mock 身份。

### 3.2 真实调用链

源码运行和便携包必须使用同一条业务调用链：

```text
Registry → TaskService → ModuleProcessRunner → modules/moisture/run_module.bat
→ draft/finalize → result.json → 主框架结果中心
```

必须满足：

- `version`、`self-check` 和 `run --job` 均经过正式 BAT；
- draft 和 finalize 是两个独立进程，finalize 使用 `parent_job_id` 重建 draft 根身份；
- 主框架读取模块实际生成的 result 和 artifacts，不允许测试代码或 UI 手工伪造结果；
- 输入快照不修改原始 Excel，输出只能位于任务 `output_dir`；
- 源码环境使用当前仓库 `.venv`，便携包使用受信任的模块 EXE，不使用系统 Python；
- XLSX 和 Markdown 的打开动作使用经过路径校验的 artifact 绝对路径。

## 4. P1：真实 AI Provider

### 4.1 Provider 组合

- Bootstrap 必须根据 `SettingsStore`、`CredentialStore` 和联网设置创建实际 Provider，不再无条件
  构造 `MockProvider`。
- 首个正式验收目标为 DeepSeek 的 OpenAI-compatible 接口；API 地址和模型名称必须可配置，
  不在代码中硬编码模型。
- API Key 只存入 Windows 安全凭据。数据库、设置文件、任务目录、Job、日志、错误提示和 Git
  均不得保存明文密钥。
- 配置缺失或非法时可以进入离线模式，但 UI 必须显示实际生效 Provider、联网状态和降级原因。
- 修改 Provider 配置后，新任务必须使用新配置；若需要重启应用，界面必须明确提示。

### 4.2 外发与降级

每次 AI 外发必须依次通过：

```text
模块声明请求 → 主框架校验 scope/payload → 脱敏预览
→ 用户对该请求逐次同意 → Provider 调用 → 结构化响应 → finalize 严格校验
```

验收要求：

- 关闭联网、用户拒绝、缺少密钥、HTTP 错误、超时、限流、非法 JSON 和响应结构错误均返回明确
  的 denied/error/timeout 降级状态；
- 服务失败不得让任务伪成功，也不得破坏模块已经生成的确定性结果；
- 日志可以记录 Provider ID、模型、耗时和状态，但不得记录密钥、完整敏感 payload 或原始响应；
- AI 响应只有通过 request ID、candidate ID、字段、方向、观测值、rule hash、evidence 和置信度
  校验后，才允许影响红/蓝辅助状态；
- 正式模块本身不得新增 `httpx`、Provider 或 API Key 依赖。

## 5. P2：知识、经验和规则治理入口

### 5.1 三类资产不得混用

| 资产 | 用途 | 是否可改变确定性判定 | 管理责任 |
| --- | --- | --- | --- |
| 主框架知识库 | 通用指导和报告引用 | 否 | 主框架负责人 |
| moisture 经验库 | 有版本和适用范围的历史经验 | 否，仅作辅助证据 | 模块业务负责人批准，框架提供入口 |
| moisture 规则库 | 公式外的正式筛查规则 | 仅 confirmed 版本可以 | 业务负责人批准，框架提供治理流程 |

主框架知识库不得代替版本化经验库，也不得把普通知识文本直接转换成红/蓝颜色或正式规则。

### 5.2 经验管理入口

框架页面应复用现有 `ExperienceManagementService` 的生命周期和校验语义，不重新发明经验模型。
至少支持：

```text
list / show / create / update / validate / publish / retire / history
```

- draft 可以修改，approved 不可原地修改；修改 approved 必须创建新版本；
- retired 不物理删除，正式运行时只检索有效期内的 approved 版本；
- 发布保存稳定 ID、版本、SHA-256、来源、作者、复核人、证据和适用范围；
- hash 冲突、ID/version 冲突、Schema 非法、路径越界和原子写失败必须拒绝操作；
- 管理端故障不得影响正式检测任务读取当前 approved 经验。

### 5.3 规则管理入口

规则页面至少支持：

```text
查看当前版本 → 创建草稿 → 编辑 → Schema/业务校验 → 测试预览
→ 负责人批准 → 发布新版本 → 停用/回滚 → 查看历史和审计
```

- confirmed 规则不可原地修改；每次变更生成新的 package ID/version/hash；
- pending_confirmation 规则不得自动参与正式判定；
- 发布前必须运行代表性脱敏样本，展示新旧结果差异和受影响记录数；
- 发布使用临时文件、fsync 和 `os.replace`，失败后旧 active 版本必须保持完整；
- 回滚通过重新激活已验证的历史版本完成，不删除失败或停用版本；
- 框架不得自行批准 `0.55/0.47` 或任何新阈值、材料范围和供应商映射。

### 5.4 管理进程边界

- 规则和经验管理使用独立管理进程或管理接口，不加入正式 `run_module.bat`；
- 管理 UI 不直接 import 模块内部 repository，不绕过模块 Schema 和 hash 校验；
- 管理接口必须使用结构化输入输出、路径包含校验、超时和原子写；
- 检测任务运行期间禁止发布新版本；至少应使用进程级互斥锁阻止运行与发布并发修改；
- 每次管理操作记录操作者、时间、旧/新版本、hash、结果和失败原因，审计中不保存敏感原文。

## 6. P3：AI 报告增强

AI 报告只能建立在模块已经计算并验证的确定性数据之上。推荐流程：

```text
确定性统计/规则结果/已验证证据 → 模块构造脱敏且限长的报告请求
→ 主框架取得逐次同意并调用 Provider → 模块校验结构和引用
→ 将通过校验的辅助摘要写入 Markdown
```

必须满足：

- AI 不重新计算含水率、均值、范围、阈值命中或颜色；
- 请求不包含完整 Excel、原始行、绝对路径、客户身份或供应商真实身份；
- AI 文本中的数值、候选和引用必须能对应确定性结果或 approved 经验；
- 无来源、未知候选、越权结论和与确定性数据冲突的内容不得写入正式报告；
- 报告明确区分“确定性结果”“知识/经验引用”“AI 辅助说明”；
- AI 不可用时仍生成完整的确定性 XLSX、Markdown 和 result，并标记未使用辅助分析；
- AI 不得生成正式不合格、责任、处罚、赔偿、放行或结案结论。

## 7. 责任矩阵

| 事项 | moisture 模块 | 主框架负责人 | 业务负责人 |
| --- | --- | --- | --- |
| Excel、公式、统计和规则执行 | 实现并测试 | 不改算法，负责安全调用 | 确认业务口径 |
| Registry、Runner、任务目录和进程隔离 | 遵守合同 | 实现和维护 | 验收可用性 |
| confirmation/request 声明和响应校验 | 实现 | 编排、展示和落盘 | 回答或批准 |
| Provider、网络、凭据和用户同意 | 不持有 | 实现、审计和部署 | 批准使用范围 |
| 主框架知识库 | 声明查询 scope | 管理、检索和返回 | 确认资料来源 |
| 经验版本和适用性 | 实现模型、校验和只读检索 | 提供管理入口和审计 | 审核发布/停用 |
| 规则版本、阈值和适用范围 | 实现加载和执行 | 提供治理流程，不代批 | 审核发布/回滚 |
| XLSX、Markdown 和颜色 | 生成并验证 | 展示和安全打开 | 确认对外措辞 |
| 打包、升级和回滚 | 提供模块资产 | 负责便携包和发布流程 | 签署验收 |

## 8. 分阶段验收

### Gate P0

- 默认 GUI 调用正式 moisture，数据库记录 `is_mock=false`；
- 正式模块失败时不回退 Mock；
- Registry → Runner → BAT → result 的 draft、批次隔离和 finalize 闭环通过；
- 源码和便携包均能打开模块生成的 XLSX/Markdown；
- 原输入 SHA-256 不变，任务目录和历史记录可追溯。

### Gate P1

- DeepSeek OpenAI-compatible 合法响应可以完成一次真实、经用户同意的请求；
- 拒绝、缺少密钥、关闭联网、超时、HTTP 错误和非法响应均安全降级；
- UI 显示实际 Provider，不存在“配置真实 Provider、实际仍调用 Mock”的情况；
- 凭据、敏感 payload 和原始响应不出现在数据库、Job、日志和 Git。

### Gate P2

- 经验 draft、修改、校验、发布、停用和历史保留通过；
- 规则草稿、差异预览、批准、发布、回滚和审计通过；
- hash/版本冲突、非法 Schema、路径越界和原子写失败不会损坏 active 内容；
- draft/retired/pending 内容不影响正式任务；运行期间无法写规则或经验库。

### Gate P3

- 合法 AI 辅助摘要只引用确定性结果和已验证证据；
- 非法数值、未知候选、无效引用和越权结论被拒绝；
- denied/error/timeout/离线模式仍输出完整确定性报告；
- 报告清楚标注 AI 辅助性质，不改变正式颜色语义。

### 最终门禁

```powershell
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable); print(sys.version)"
.\.venv\Scripts\python.exe -m app.tools.module_contract_cli validate modules/moisture
modules\moisture\run_module.bat version
modules\moisture\run_module.bat self-check
.\.venv\Scripts\python.exe -m pytest modules\moisture\tests -q
powershell -ExecutionPolicy Bypass -File scripts\verify_repo.ps1
git diff --check
git status --short
```

另需执行 P0—P3 对应的主框架定向集成测试和便携包真实进程验收，不得仅以模块内部测试替代
主框架调用。

## 9. 禁止事项

- 不把正式 moisture 复制到 `mock_modules/moisture` 形成双实现；
- 不在 Provider 失败时静默使用 Mock 并冒充真实 AI；
- 不把 API Key 写入源码、环境示例、数据库、Job、日志或交付包；
- 不让主框架直接修改 active 规则文件或 approved 经验文件；
- 不为实现管理 UI 而降低 Schema、hash、路径、版本和原子写校验；
- 不让 AI 或普通知识文本直接修改公式、阈值、确定性颜色或责任结论；
- 不提交客户原始 Excel、真实供应商身份、绝对路径、运行日志或 Provider 原始响应；
- 不在 P0 未通过前同时推进 P1—P3，避免把接入错误误判为业务或 Provider 错误。

## 10. 交付要求

每个阶段由框架负责人单独提交，并提供：

- 设计和责任边界说明；
- 变更文件和提交号；
- 定向测试、失败降级测试和真实进程验收结果；
- 安全检查、已知限制和回滚方法；
- 需要业务负责人签署的规则、经验或报告措辞清单。

只有 Gate P0—P3 和最终门禁全部通过，才能声明“正式 moisture 接入、真实 AI、治理入口和
AI 报告增强已经完成”。
