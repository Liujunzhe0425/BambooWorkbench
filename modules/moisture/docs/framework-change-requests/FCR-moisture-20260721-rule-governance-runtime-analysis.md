---
request_id: FCR-moisture-20260721-rule-governance-runtime-analysis
module_id: moisture
module_version: 0.1.1
owner: moisture模块负责人
status: proposed
framework_areas:
  - ui
  - service
  - storage
  - workflow
  - security
  - packaging
breaking_change: false
required_before_module_merge: false
---

# 框架适配请求：水分规则治理、任务规则快照与人工复核

> 本请求不阻塞当前 moisture v0.1.1 的既有接入；阶段 A/B 的模块离线治理内核也可先独立开发。
>
> 在受治理规则进入正式运行、Knowledge→AI 编排或人工复核上线前，本请求必须获批并完成相应阶段。
>
> 完整设计见：[`../architecture/moisture-next-stage-architecture.md`](../architecture/moisture-next-stage-architecture.md)。

## 1. 业务目标与使用场景

### 1.1 规则治理

质量和实验负责人需要把企业知识、模块 approved 经验、历史检测数据和人工复核标签组合起来。moisture 模块用确定性程序计算统计和有限候选，AI 只能选择已知 `calculation_id` 并解释，随后经历史回放、冲突检查和人工批准形成可追溯、可回滚的规则版本。

候选、回放规则和 rejected 规则不能直接进入日常检测。框架必须把治理操作与正式任务隔离，并保证只有人工批准、哈希合法且原子发布的规则包可以成为新任务的固定快照。

### 1.2 日常检测与复核

实验人员继续使用现有 moisture 模块处理 Excel。模块负责含水率、统计、规则命中和报告；Knowledge/AI 只提供辅助证据。实验人员可在框架中保存最终复核记录，记录仅作为下一轮显式创建历史数据集时的候选标签，不自动修改规则、经验、原始 Excel 或既有 artifacts。

### 1.3 颜色业务方向

下一业务版本停止生成红/蓝：20列主表只保留确定性橙/绿，AI 内容进入“模型分析记录”和 Markdown 的“AI辅助分析（非结论）”。该行为由 moisture 模块实现和验收。框架不得根据 AI 文本自行着色，也不得回写或重算 v0.1.1 历史红/蓝结果。

## 2. 当前限制

1. `modules/moisture/rules/active/` 是模块内只读静态资产，无候选、回放、批准、发布、active binding 和回滚工作流。
2. 当前规则包已有版本、来源、scope、机器批准状态和 `rules.yaml` SHA-256，但框架没有保存数据集、回放、批准人、package 整体 SHA-256 和发布审计。
3. 框架没有受控历史数据集、候选规则、回放报告、已发布版本、active binding 和人工复核的存储模型。
4. 当前任务创建不生成规则/趋势快照；Draft/Finalize 读取模块当前 active 目录，不能在发布切换期间证明使用同一版本。
5. 当前 v0.1.1 的模块配置只接受 `default_year`，直接增加 `rule_snapshot` 等字段会触发 `configuration contains unknown fields`。
6. 中央 Module Manifest 没有治理工作器能力字段，框架也没有独立的模块治理进程宿主。
7. Knowledge 和 AI 请求目前独立处理，没有 request dependency、Knowledge证据版本绑定和 Knowledge→AI 顺序编排。
8. Provider 配置或调用异常并非所有路径都保证形成结构化 `error`/`timeout` 响应。
9. Knowledge 记录缺少完整的版本、内容 SHA-256、来源和业务批准状态，不能形成稳定证据快照。
10. 当前框架没有实验人员最终复核队列和 `HumanReviewRecord`。
11. 当前 `0.47/0.55` 在机器规则包中为 confirmed，但业务文档仍标记待批准；不得把机器状态当成新治理系统的业务批准证据。

## 3. 请求的框架改动

### 3.1 必须具备

#### A. 模块治理工作器宿主与能力协商

框架支持可选的模块私有治理能力文件，但不修改中央 `module.json` Schema。能力文件至少声明：

- module ID；
- 治理工作器相对入口；
- `moisture-governance/1.0` 协议版本；
- `moisture-runtime-context/1.0` 支持状态。

框架要求：

- 能力文件的 module ID 必须与 Registry 发现结果一致；
- 入口必须是模块目录内普通文件，不接受绝对入口、symlink、junction 或 reparse point；
- 以独立进程调用，不 import 模块内部 Python；
- request/response、输入目录和临时文件限制在本次治理工作目录；
- 捕获 stdout 进度 JSON 和 stderr 诊断，支持超时、取消和故障隔离；
- 无能力声明的旧模块不显示治理按钮，也不接收扩展配置；
- 便携/安装版调用随模块打包的治理可执行文件，不依赖系统 Python。

模块方将在后续阶段实现以下私有操作：

```text
validate_dataset
compute_statistics
build_catalog
compile_proposal
replay
build_package
```

框架只负责进程、文件、状态和审计，不解释统计或回放结果。

#### B. 规则治理中心

新增独立页面与应用服务：

```text
导入受控数据集 → 模块确定性统计 → AI候选
→ 模块候选编译 → 模块历史回放/冲突检查
→ 人工批准/拒绝 → 发布 → 历史查看/回滚
```

强制要求：

- 未配置最低样本量、最大误报率和最低召回率时可以试算和影子回放，但不能批准或发布；
- AI只能引用工作器生成的 `calculation_id`，框架页面不提供编辑AI阈值的控件；
- 批准页面不能编辑候选，内容变化必须新建候选版本并重新回放；
- 首期为单人审批，记录本地审计操作人、时间、理由、数据集/候选/回放哈希；
- 本地审计操作人不宣称等同强身份认证或角色授权；
- rejected、未回放和临时规则永远不能成为 active；
- 只有发布服务能够写不可变规则版本和切换 active binding。

#### C. 不可变治理存储、active binding 与任务快照

- 在框架数据根目录建立 governance 文件区，不写模块安装目录；
- 大文件、Excel、规则包、统计快照和回放报告存为不可变文件，数据库只保存元数据、引用、状态和审计；
- 每个版本记录规范化算法版本、package/rules SHA-256、数据集/候选/回放哈希和批准记录；
- Phase 1 每个 module active binding 指向一个完整规则包，包内规则自行声明 scope；
- 框架不得在解析 Excel 前按供应商/材料选择规则包；
- active binding 使用数据库事务或等价原子操作切换，失败时旧 active 完整可用；
- 创建支持 runtime-context 的 moisture 任务时，将 active 包复制到 root task 的 `protocol/runtime-context/`；
- Draft/Finalize 读取同一只读配置和快照；全局 binding 后续变化不影响进行中任务；
- 快照哈希或路径校验失败时明确失败，不静默改用新 active；
- 旧任务、旧 artifacts 和历史红/蓝结果保持只读。

#### D. 扩展模块配置的版本协商

当前 v0.1.1 仅接受 `default_year`。框架只有在模块能力文件明确声明 `moisture-runtime-context/1.0` 后，才生成扩展 `module_config_file`：

```json
{
  "config_schema_version": "2.0",
  "default_year": 2026,
  "rule_snapshot": {
    "path": "<task-local-absolute-path>/protocol/runtime-context/rules",
    "package_sha256": "<64-lowercase-hex>",
    "rules_sha256": "<64-lowercase-hex>"
  },
  "history_context": {
    "path": "<task-local-absolute-path>/protocol/runtime-context/history.json",
    "sha256": "<64-lowercase-hex>"
  }
}
```

兼容要求：

- 能力文件缺失、版本未知或模块版本不支持时，只生成旧格式配置；
- 不允许通过“先传新字段、失败后重试旧字段”探测能力；
- 扩展路径必须位于 root task，且 Draft/Finalize 完全一致；
- module config 和快照随 root task 恢复，不从全局 active 重建。

#### E. Knowledge → AI 依赖编排与结构化降级

中央 service 类型仍为 `knowledge` 和 `ai`。模块在 AI payload 中使用私有依赖字段：

```json
{
  "dependencies": [
    {"service": "knowledge", "request_id": "<knowledge-request-id>", "required": false}
  ]
}
```

框架要求：

- 校验依赖 request ID 存在、唯一、service 类型匹配且属于同一 root job；
- 先执行 Knowledge，再执行依赖它的 AI；
- 每个请求在 `service-response.json` 中保留独立响应项和原 request ID；
- 不修改 result 中模块声明的原始 service request；只为 Provider 构造临时 gateway payload；
- Knowledge ref 使用 `knowledge:<record-id>:<version>:<sha256>`；
- 模块提供的 approved 经验证据已完成 scope 过滤，框架只运输，不重新判断适用性；
- `required=false` 时 Knowledge 失败可继续无 Knowledge 的 AI；`required=true` 时 AI 形成结构化 error；两种情况均继续确定性 Finalize；
- denied、缺少密钥、Provider配置错误、HTTP错误、限流、超时和非法响应均转换为结构化状态，不抛出导致任务丢失的未处理异常；
- 保留现有脱敏预览、逐次联网同意和 API Key 隔离。

#### F. Knowledge 治理元数据

- Knowledge记录增加稳定 ID、版本、内容 SHA-256、来源、启用/批准状态和更新时间；
- 治理和运行任务使用不可变 Knowledge 证据快照；
- 旧记录迁移为 `legacy` 来源，不静默获得业务 approved 身份；
- 删除或停用记录不改变已经完成的任务和回放证据。

#### G. 人工复核中心

- 提供 moisture 疑似批次复核队列；
- 支持 `confirmed_normal`、`confirmed_anomaly`、`retest_required`、`inconclusive`；
- 保存 task、batch、疑点、规则版本/哈希、AI报告哈希、审计操作人、时间、结论和说明；
- `confirmed_anomaly` 和 `retest_required` 要求非空说明；
- 复核不修改原始 Excel、模块 XLSX/Markdown、result 或已发布规则；
- 只有用户显式创建新数据集版本时，确定标签才可进入下一次回放。

### 3.2 页面与交互

#### 规则治理页

- 区域：数据集、统计快照、候选、回放、审批、已发布版本、active版本、审计历史；
- 操作：导入、试算、请求AI候选、回放、批准、拒绝、发布、回滚；
- 校验：操作人、批准理由、治理门槛、数据集/候选/回放版本和全部哈希；
- 空状态：无数据集、无标签、样本不足、无门槛、无候选、无发布版本分别说明；
- 错误状态：哈希不一致、Schema非法、工作器失败、冲突、Provider不可用和发布失败均保留旧 active；
- 展示：新旧规则差异、受影响批次、混淆矩阵、标签覆盖、留出集表现和冲突明细。

#### 人工复核页

- 区域：待复核列表、确定性规则命中、AI辅助分析、证据引用、历史趋势和复核表单；
- 明确分层显示“确定性初筛”“AI辅助分析”“人工最终复核”；
- 不把AI优先级显示为正式异常、不合格、责任或放行结论；
- 新结果不要求红/蓝展示；历史红/蓝按原 artifact/result 只读显示并标注“旧版辅助证据状态”。

### 3.3 中央合同边界

- `JobRequest`、`ModuleResult`、Confirmation、Service Request/Response 中央 Schema 保持不变；
- Service Request 的 `payload` 已允许模块私有对象，但新私有字段必须由 moisture 自有 Schema 严格校验；
- 治理 request/response、runtime context 和 AI dependency 使用模块私有 Schema；
- 不新增中央 service 类型和退出码；
- 服务失败通过 response status 和 result errors 降级；
- 非moisture模块忽略并且不会收到上述私有协议。

### 3.4 数据生命周期、恢复和打包

- 导入前检查文件数、单文件/总大小和剩余空间；限额由框架配置并在页面显示；
- 被 published rule 引用的数据集、统计和回放报告不可物理删除，只能归档/停用；
- 未引用草稿可按明确保留策略人工删除，删除需审计且先校验路径包含关系；
- 数据库备份恢复后必须复核治理文件哈希，数据库和文件不一致时禁止发布；
- 应用异常退出后旧 active 和已完成任务可恢复；
- 便携/安装版包含治理页面、迁移和模块治理工作器，但不打包客户数据、历史规则、审计记录或密钥；
- 模块运行时不访问框架数据库。

## 4. 责任边界

### 模块方已经完成

- Excel解析、公式复核、批次统计、只读规则加载和 Evaluator；
- approved经验检索、Draft/Finalize、Knowledge/AI请求和响应严格校验；
- 确定性报告和共享服务降级基础。

### 等待框架提供

- 治理工作器宿主和能力协商；
- 治理UI、不可变存储、数据库审计、active binding、任务快照和恢复；
- Knowledge→AI编排、Provider结构化降级和Knowledge治理元数据；
- 人工复核页面、记录、数据生命周期和打包。

### 仍由模块方负责

- 跨批次 Decimal 统计、候选计算、规范化/哈希业务实现；
- 候选编译、回放、冲突和scope算法；
- 模块私有 Schema、任务上下文和AI业务响应校验；
- 下一版本取消红/蓝、20列主表和报告呈现的业务正确性。

### 需要业务负责人确认

- 当前 `0.47/0.55` 的批准/撤销/转候选；
- 最低样本量、误报率、召回率、scope优先级和样本不足策略；
- 人工复核语义及其与“不合格/责任”的边界；
- Knowledge、经验、趋势外发范围和审计保留期限；
- 本地单人审批是否满足试点要求；
- 红/蓝取消的目标版本和历史展示文案。

## 5. 数据、安全与权限

- 历史 Excel、复核标签、知识和经验属于企业业务数据，只保存到框架受控数据根目录；
- 每个文件、数据集、统计、候选、回放、规则包和运行上下文保存 SHA-256；
- AI外发仅包含脱敏、限长、来源可追溯的统计摘要和证据摘录，不发送完整Excel、原始行或绝对路径；
- API Key继续只由框架凭据存储管理，不进入治理文件、数据库、任务、日志或Git；
- 发布服务具有独立写能力，普通任务、AI和Knowledge只有读取任务快照的能力；
- 日志只记录ID、版本、哈希、耗时和状态，不记录敏感原文或Provider完整响应；
- 首期本地操作人仅用于审计，不冒充登录、角色或强认证；
- 文件操作必须拒绝 `..`、symlink、junction、reparse point 和路径越界。

## 6. 兼容性与迁移

- 是否破坏中央合同：否；
- 是否兼容当前 v0.1.1：是，未声明能力时继续使用模块内 `rules/active/` 和旧配置；
- 旧任务/result/artifacts：只读保留，不补写新快照或人工复核，不重算历史红/蓝；
- 框架未升级：现有确定性检测继续运行，但不能宣称具备治理发布和人工复核；
- 当前规则迁移：`0.47/0.55` 不自动成为新治理系统 approved；
- 回滚：active binding 指回历史已验证版本，不删除新旧版本；
- 进行中任务：继续读取 root task 固定快照；
- 非moisture模块：不得收到私有配置或治理操作。

## 7. 验收标准

1. 无治理能力文件的 v0.1.1 继续正常 draft/finalize，框架不下发扩展配置；
2. 能力文件 module ID、入口或协议非法时 Registry 拒绝治理能力，但不影响模块现有日常运行；
3. 框架经独立进程调用治理工作器，工作器不能访问本次治理目录外的路径；
4. 同一冻结数据集重复试算得到相同统计、候选、回放结果和 SHA-256；
5. AI返回自由阈值、未知 calculation/evidence/Evaluator 时编译失败，active 不变；
6. 未配置或未达到业务门槛时可查看回放但不能批准/发布；
7. 通过回放的候选批准记录操作人、理由、时间和全部哈希，发布后新任务使用该版本；
8. 发布中断、数据库事务失败或应用退出时旧 active 保持可用；
9. 回滚后新任务使用旧版本，回滚前任务仍使用固定版本；
10. Draft/Finalize 的 package ID、版本和 SHA-256 一致，快照篡改时明确失败；
11. 同一任务 Knowledge 先于依赖AI，request/response ID和证据哈希可交叉验证；
12. AI拒绝、缺密钥、Provider配置错误、HTTP错误、限流、超时或Knowledge不可用时仍产生确定性 XLSX、Markdown 和 result；
13. 下一业务版本主表只使用确定性橙/绿，AI不能改色；v0.1.1历史红/蓝仍可只读打开；
14. 20列主表、公式、均值、区间和现有确定性基线不因框架治理改动而变化；
15. 人工复核完整保存任务、批次、规则/AI哈希、操作人、结论、时间和说明，不修改输入或 artifacts；
16. 只有显式创建新数据集时，确定人工标签才进入回放；
17. 非moisture模块和旧版本模块仍按原合同创建、完成和恢复任务；
18. 无系统Python的安装/便携版能够调用治理工作器、固定规则快照并完成服务离线降级；
19. 数据库恢复后治理文件哈希复核通过才允许发布；
20. API Key、客户原始Excel、绝对路径、Provider原始响应不出现在审计、日志、任务结果或交付包。

## 8. 备选方案与影响

- 直接修改 `modules/moisture/rules/active/`：缺少权限隔离、任务固定、审计和原子回滚，不采用；
- 用 task confirmation 代替规则审批：缺少版本、回放和长期治理语义，不采用；
- 由AI直接输出阈值/代码：违反确定性和最小权限，不采用；
- 框架 import moisture 内部实现：破坏进程隔离和模块边界，不采用；
- 按供应商建立单一 active binding：任务创建前未知Excel scope且批次可能混合，不采用；首期采用每模块一个完整 scoped package；
- 框架自行查询模块经验库：会复制scope语义，不采用；由模块输出已过滤证据包；
- 影响框架范围：`core/storage`、`core/tasks`、`core/services`、`core/knowledge`、`ui/pages`、Bootstrap与打包；
- 影响其他模块：中央合同不变，但数据库迁移、能力缺失回退和共享服务降级必须覆盖 boiling/after_sales；
- 主要风险：历史标签偏差、scope稀疏、发布竞争、知识外发、单人审批、迁移/恢复失败和旧任务兼容。

## 9. 附件与证据

- 架构设计：[`../architecture/moisture-next-stage-architecture.md`](../architecture/moisture-next-stage-architecture.md)；
- 当前规则包：`modules/moisture/rules/active/rule-package.json`、`rules.yaml`；
- 当前规则 Schema：`modules/moisture/schemas/rule-package.schema.json`；
- 当前 AI 响应 Schema：`modules/moisture/schemas/ai-review-response.schema.json`；
- 当前框架限制：[`../framework-issues.md`](../framework-issues.md)；
- 当前维护说明：[`../架构与开发维护指南.md`](../架构与开发维护指南.md)；
- 脱敏基线：21份历史文件、166个样本、公式复核差异0、1高1低19正常；
- 相关 issue/PR：待框架负责人受理后填写。

## 10. 框架方审核（由框架负责人/Codex填写）

- 审核结论：待审核
- 判断理由：待填写
- 实施分支/PR：待填写
- 验证范围：待填写
- 对模块交付的后续要求：待填写
