> 文档状态：历史归档
> 不作为当前实现和验收依据。
> 当前有效说明以 README 和三份主指导文档为准。

---
request_id: FCR-moisture-20260723-ai-report-context-selection
module_id: moisture
module_version: 1.0.1
owner: moisture模块负责人
status: implemented
framework_areas:
  - ui
  - service
  - storage
  - workflow
  - security
breaking_change: false
required_before_module_merge: false
---

# 框架适配请求：独立AI报告及经验、历史数据选择

> 本请求只覆盖moisture v1.0.1独立AI报告入口。
> 不请求规则管理、候选规则、历史追加或完整三功能工作台。
> 模块开发计划见：[`../architecture/moisture-v1.0.1-independent-ai-report-plan.md`](../architecture/moisture-v1.0.1-independent-ai-report-plan.md)。

## 1. 业务目标

moisture v1.0.1将普通汇总生产和AI分析拆开：

- 普通汇总任务只生成确定性四表XLSX、基础Markdown和result；
- 不再生成“模型分析记录”工作表；
- 不再执行AI辅助复判或红蓝提升；
- 用户需要进一步分析时，单独进入“AI汇总报告”；
- 用户选择当前汇总表、历史数据、approved经验并输入问题；
- AI结果保存为独立Markdown和JSON，不修改原汇总表。

该拆分用于减少技术字段对业务汇总表的干扰，并让AI分析成为用户主动发起、数据范围清楚、可独立追溯的操作。

## 2. 模块方负责内容

moisture负责：

- 四表汇总和取消普通任务AI复判；
- 当前/历史汇总表业务校验和聚合统计；
- 轻量历史资料索引、SHA-256去重和retired状态；
- approved经验候选目录和scope/有效期判断；
- AI分析上下文、脱敏、预算、稳定request ID；
- service request声明和service response严格校验；
- `ai_analysis_report.md`、`ai_analysis_result.json`生成；
- 所有AI失败路径的业务降级。

框架不得重新实现上述水分业务语义。

## 3. 请求的最小框架能力

### 3.1 一个独立入口

在moisture模块页面增加一个“AI汇总报告”入口。第一版只包含：

1. 当前汇总表选择；
2. 历史数据导入和多选；
3. approved经验多选；
4. 用户问题输入；
5. 脱敏预览；
6. “同意并开始分析”按钮；
7. 任务状态、降级原因和结果文件展示。

不得把该入口混入普通汇总任务，也不得默认自动调用AI。

### 3.2 输入和选择状态

页面要求：

- 当前汇总表为必选，只接受moisture声明支持的 `.xlsx`；
- 历史数据为可选，可导入多个标准汇总表并按日期范围多选；
- 经验为可选，只显示模块返回的approved且当前有效条目；
- 用户问题为必填，限制合理字符数；
- 显示所选当前表、历史条目数量、时间范围、经验ID/标题/版本；
- 不显示本机绝对路径，使用安全显示名；
- 提交前允许取消或重新选择。

历史和经验的校验结果必须来自模块管理进程；框架不解析Excel、不判断经验scope。

### 3.3 模块数据目录和窄化管理进程

框架为moisture分配受控模块数据目录，仅保存：

- 历史汇总表只读副本；
- 历史资料JSON索引；
- AI分析任务所需的临时上下文和最终产物引用。

框架提供一个窄化的模块管理进程宿主，仅调用：

- `list_approved_experiences`；
- `import_history_summary`；
- `list_history_summaries`；
- `retire_history_summary`。

本期不包含经验编辑、规则编辑、发布、回滚、任务规则快照或其他治理操作。

进程要求：

- 使用模块声明的独立入口，不import模块Python；
- 请求、响应和临时目录均由框架创建；
- 只能访问本次工作目录和显式授权的moisture数据目录；
- stdout仅接收进度JSON，stderr保存脱敏诊断；
- 支持超时、取消和故障隔离；
- 管理失败不得损坏已有历史索引或影响普通汇总任务；
- 源码使用仓库 `.venv`，便携版使用随包运行时，不回退系统Python。

### 3.4 AI任务编排

框架复用现有Job、TaskService、service request/response和Provider能力：

1. 根据页面选择创建独立 `ai_report` 模块任务；
2. 模块draft校验输入并声明至多一个AI service request；
3. 框架展示模块生成的脱敏预览；
4. 用户逐次同意后，框架调用当前生效Provider；
5. 框架把结构化response交给独立finalize；
6. 模块校验并生成独立报告；
7. 框架展示任务状态并允许打开Markdown/JSON。

中央 `JobRequest`、`ModuleResult`、Confirmation和Service Request/Response Schema保持不变。操作选择通过moisture私有、版本化配置表达。

### 3.5 结果展示

结果中心显示：

- `ai_analysis_report.md`；
- `ai_analysis_result.json`；
- Provider状态；
- 使用的当前汇总表显示名和内容哈希；
- 历史数据范围和条目数；
- 经验ID、版本和哈希；
- denied/error/timeout/非法响应的公开降级原因。

页面必须明确：AI报告是辅助分析，不改变汇总表中的确定性结果，也不形成正式不合格、责任、处罚或放行结论。

## 4. 数据与安全边界

- API Key继续只由框架CredentialStore保存；
- 每次外发必须经过联网开关、脱敏预览和用户逐次同意；
- 框架不得向Provider追加完整Excel、原始行或绝对路径；
- 模块给出的payload不得被框架扩展为更大数据集；
- 供应商身份默认匿名，明文外发需另行获得业务批准；
- 历史文件保存在本地受控目录，不建设网络资料库；
- 任务和日志不保存API Key、Provider授权头或完整原始响应；
- 路径必须拒绝 `..`、symlink、junction、reparse point和目录越界；
- denied、缺少密钥、配置错误、HTTP错误、限流、超时或非法响应不得导致普通汇总成果损坏。

## 5. 兼容与降级

- v1.0.0及更早普通任务和历史成果只读保留；
- 新AI入口未完成或不可用时，v1.0.1普通四表汇总仍可独立运行；
- 历史资料为空时允许只分析当前汇总表；
- approved经验为空时允许无经验分析，并在结果中说明；
- 用户拒绝联网时生成结构化denied结果，不伪造AI报告；
- Provider失败时显示降级原因，不自动切换为Mock并冒充真实分析；
- 非moisture模块不接收私有配置或管理操作。

## 6. 本期明确不请求

- 完整三功能首页；
- 历史汇总表追加新原始数据；
- AI候选规则生成；
- 规则草稿、发布、停用、恢复或任务规则快照；
- 经验编辑UI；
- 数据库、登录、角色、多人审批和在线协作；
- 新中央Schema、service类型或退出码；
- 框架修改水分公式、阈值、颜色或报告正文。

上述能力后续分别提交独立FCR，不与本期入口捆绑。

## 7. 验收标准

1. 普通汇总任务不自动调用AI，仍能生成合法四表XLSX、Markdown和result；
2. AI入口必须由用户主动打开并提交；
3. 当前汇总表缺失或非法时不创建Provider调用；
4. 历史五表和新四表均可由模块校验后选择；
5. draft/retired经验不显示，approved经验选择可追溯；
6. 外发预览不含完整Excel、原始行、绝对路径或未授权身份；
7. 用户同意后才允许Provider调用；
8. 合法响应生成独立Markdown/JSON且原汇总表SHA-256不变；
9. denied、缺密钥、错误、限流、超时和非法响应均形成清楚降级结果；
10. 历史导入重复、路径越界或原子写失败不损坏既有资料；
11. 无历史或无经验时仍可完成当前表分析；
12. 便携版不依赖系统Python，且不包含客户数据、历史资料或凭据；
13. 其他模块、中央合同和普通moisture汇总流程不受影响。

## 8. 未实现时的降级方式

如果本FCR尚未获批或框架入口未完成，模块仍可先交付四表确定性汇总和模块侧AI上下文/响应校验测试，但不得在GUI中宣称独立AI报告已经可用。

## 9. 框架方审核

- 审核结论：已批准并完成最小适配
- 判断理由：框架提供独立 AI 报告入口、管理进程宿主、受控模块数据目录、历史/approved 经验选择和现有 Provider 编排；未把水分业务算法迁入框架。
- 实施分支/PR：PR #43，已合入 `integration`（`65561e0`）
- 可复用的现有接口：待填写
- 对模块v1.0.1交付的前置要求：待填写
