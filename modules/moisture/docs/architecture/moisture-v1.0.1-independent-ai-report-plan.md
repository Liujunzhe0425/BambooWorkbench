# moisture v1.0.1 独立AI报告实施记录

> 状态：模块与框架联合实现完成，最终交付门禁进行中
> 目标版本：`1.0.1`
> 修改边界：模块实现只允许修改 `modules/moisture/`
> 本计划不执行客户第一轮要求中的 `analysis_report.md` 表达整改；该事项另行排期。

## 1. v1.0.1目标

v1.0.1完成一次明确的业务拆分：

1. 汇总表生产只负责Excel解析、公式复核、Decimal统计、规则初筛和确定性报告；
2. `moisture_summary.xlsx` 从五张工作表调整为四张，删除“模型分析记录”；
3. 普通汇总任务不再声明AI辅助复判请求，不再由AI把橙/绿升级为红/蓝；
4. AI能力迁移为独立的“AI汇总报告分析”任务；
5. 用户在独立任务中选择当前汇总表、历史数据、approved经验并输入问题；
6. AI结果作为独立Markdown和JSON交付，不修改汇总表。

当前v1.0.0成果保持只读兼容，不回写或重新计算历史“模型分析记录”和红蓝状态。

## 2. 目标用户流程

### 2.1 汇总表生产

```text
选择原始检测Excel
→ 确定性解析和计算
→ 规则初筛与日期排序
→ 输出四表 moisture_summary.xlsx
→ 输出确定性 analysis_report.md 和 result.json
```

四张工作表固定为：

1. 竹丝含水率统计；
2. 异常分析明细；
3. 趋势分析；
4. 来源追溯。

普通汇总任务不调用AI，也不输出“模型分析记录”。

### 2.2 独立AI报告

```text
选择当前汇总表
＋选择历史数据范围（可选）
＋选择approved经验（可选）
＋输入分析问题
→ 模块校验并生成脱敏上下文
→ 主框架展示外发预览和逐次同意
→ 主框架调用Provider
→ 模块严格校验响应
→ 输出独立AI报告和结构化结果
```

AI报告不改变原汇总表、规则命中、颜色或确定性报告。

## 3. Codex与Claude Code＋DeepSeek混合开发规则

### 3.1 固定分工

| 执行者 | 负责内容 |
| --- | --- |
| Codex | 架构冻结、调用链审计、普通汇总去AI化、私有配置/请求/响应合同、隐私和路径边界、主框架联调、最终门禁与交付审查 |
| Claude Code＋DeepSeek | 在Codex冻结接口后完成边界清晰的writer/validator、文件式repository、模板、fixture、局部测试和文档证据 |
| 框架负责人 | 根据获批FCR在独立框架分支实现页面、模块数据目录、管理进程宿主和TaskService/Provider编排 |

固定执行顺序为：

```text
Codex冻结任务边界
→ Codex写明CC任务输入、允许文件和验收命令
→ Claude Code＋DeepSeek完成一个小任务并写日志
→ Codex审查差异和定向测试
→ 进入下一个任务
```

禁止Codex和Claude Code同时编辑同一工作区。CC＋DeepSeek不得自行扩大任务、修改框架、改变公式/阈值或把测试期望改成迎合错误结果。

同一失败最多自主修复两轮；仍不能解释时停止并在日志中记录阻塞，由Codex或负责人判断。

### 3.2 日志目录和格式

全部开发记录写入仓库外目录：

```text
D:\codexprogram\竹丝水分检测框架适配开发\日志\moisture-v1.0.1\
```

固定文件：

- `00-context-handoff.md`：Codex维护的项目上下文，CC＋DeepSeek每次开始前必须完整阅读；
- `01-development-log.md`：按时间追加的批次总日志；
- `task-<任务ID>-<executor>.md`：单任务详细记录和交接结果。

每条任务日志至少记录：

- 时间、执行者、分支和开始HEAD；
- 任务目标、允许修改文件和明确禁止项；
- 实际修改文件；
- 实际运行命令和结果摘要；
- 失败、修复轮次和未解决问题；
- 人工对照结论；
- 结束HEAD或未提交状态；
- 下一任务的前置条件。

日志不得保存API Key、Authorization Header、客户原始Excel、真实供应商身份、完整Provider响应、本机临时任务绝对路径或大段无关pytest输出。只记录脱敏摘要、稳定ID、哈希和失败重点。

### 3.3 环境与Git约束

所有Python命令显式使用：

```powershell
.\.venv\Scripts\python.exe
```

禁止裸 `python`、`py`、系统Python和全局依赖。每位执行者开始前先验证解释器和pytest版本。

正常实现只修改 `modules/moisture/`。日志目录位于仓库外，不加入Git。不得修改或提交 `app/`、`core/`、`ui/`、`contracts/`、`packaging/`、`.github/`和其他模块。

## 4. 主框架适配前：模块独立开发

### C0（Codex）：冻结业务边界和调用图

- 目标版本固定为 `1.0.1`，不得使用 `1.1.0`；
- 保留公式、Decimal精度、阈值、日期排序、19列主表和现有四张保留表内容；
- “模型分析记录”不迁移字段到其他工作表；
- AI复判状态、置信度、AI理由和降级原因不再写入汇总Excel；
- 规则初筛颜色只来自确定性规则；
- 旧v1.0.0工作簿仍可作为历史输入读取，但新产物只输出四表。

Codex同时列出AI复判的全部生产调用方、输出字段和测试，冻结可删除、暂留兼容和必须迁移到独立报告的边界。C0完成前，CC不得修改writer或orchestrator。

### C1（Codex）：汇总任务去AI化

调整普通draft/finalize编排：

- 不再从批次构建AI review candidates；
- 不再为普通汇总任务声明AI service request；
- 不再读取或应用AI review response；
- finalize仍处理真实业务confirmations，并保持结果中的confirmations/service_requests为空；
- 移除红蓝提升路径，新结果只呈现确定性橙/绿或无色；
- 保留旧响应校验代码只限兼容读取需要；确认无合法调用方后再单独删除，不在第一轮机械清理中扩大范围。

现有Knowledge请求若只服务于AI复判，应随复判路径停用；若仍被确定性Markdown合法引用，必须通过定向测试证明其独立价值，否则不在普通汇总任务中声明。

### S1（Claude Code＋DeepSeek）：四表Excel输出

- `REQUIRED_SHEET_NAMES`改为四表；
- writer停止创建“模型分析记录”；
- workbook validator、验收fixture、工作簿合同测试和字段断言同步更新；
- 保持主表、异常明细、趋势分析和来源追溯现有列、排序、格式、图表及规则染色；
- 输入Excel和历史v1.0.0产物不被修改。

S1只允许修改writer、workbook validator及其直接测试/fixture。Codex在S1完成后核对四表关键值、日期排序、图表、颜色和输入SHA-256。

### C2（Codex）：版本化私有操作和AI报告合同

模块私有配置增加严格、版本化的操作选择：

- `summary`：默认兼容模式，生产四表汇总；
- `ai_report`：独立AI报告模式。

未提供操作字段时按 `summary` 执行。未知字段、未知操作或不合法路径明确失败。中央Job/Result Schema不变。

`ai_report`配置只保存输入角色和用户选择的稳定标识，不保存API Key、Provider配置或完整经验内容。

### S2（Claude Code＋DeepSeek）：历史数据资料库

实现模块私有、文件式轻量资料库：

- 导入模块生成的标准汇总表；
- 兼容读取v1.0.0五表和v1.0.1四表；
- 校验工作表、核心列、日期范围和业务数据类型；
- 保存只读副本及轻量JSON索引；
- 索引记录稳定ID、来源显示名、日期范围、批次数、格式版本、SHA-256和active/retired状态；
- 相同SHA-256不重复导入；
- 已导入文件不原地覆盖，retired历史仍保留；
- 写入采用临时文件和 `os.replace`；
- 拒绝绝对路径泄漏、`..`、symlink、junction、reparse point和目录越界。

历史资料不参与重新计算当前汇总表，只为AI趋势和对比摘要提供数据。

S2在Codex冻结索引Schema、路径根和原子写规则后实施repository及局部测试，不负责页面、数据库或AI请求。

### S3（Claude Code＋DeepSeek）：approved经验目录和报告模板

复用现有 `ExperienceManagementService` 和运行时approved经验语义：

- 提供只读候选目录：ID、标题、版本、scope、有效期和SHA-256；
- 页面只能选择approved且当前有效的经验；
- draft和retired经验不出现在可选列表，也不能进入AI上下文；
- AI请求只包含必要、限长的经验摘录；
- 独立报告记录实际引用的经验ID、版本和SHA-256；
- 本期不请求经验编辑页面，继续使用现有离线管理工具。

S3复用现有ExperienceRepository/ManagementService，不建立第二套经验模型。报告模板和fixture只能使用脱敏内容。

### C3（Codex）：独立AI报告内核和适配前门禁

模块读取当前汇总表、选定历史资料、approved经验和用户问题后，构建确定性上下文摘要：

- 当前周期批次数、正常/疑似数量和主要趋势；
- 与选定历史范围的聚合比较；
- 需要人工复核的有限批次摘要；
- 已批准经验的有界摘录；
- 当前启用规则的说明和哈希；
- 用户问题。

隐私和预算要求：

- 不发送完整Excel、原始行、绝对路径或文件修改时间；
- 供应商身份默认使用稳定匿名标识，只有业务批准后才允许明文；
- payload使用UTF-8字节预算并保存总数、发送数和省略数；
- request ID绑定root job、输入内容哈希、历史选择、经验选择和规则哈希，不使用时间或UUID；
- `requires_user_consent=true`；
- 模块不直接访问Provider、网络或凭据。

合法响应输出：

- `ai_analysis_report.md`：业务人员阅读的独立辅助报告；
- `ai_analysis_result.json`：状态、request ID、输入摘要哈希、历史/经验引用、校验结果和降级原因。

报告至少包含总体情况、历史比较、需复核批次、可能原因、建议步骤、证据引用和“非质量结论”声明。

denied、error、timeout、缺失或非法响应时，仍输出结构化结果和清楚的不可用说明，不生成伪造分析，不修改当前汇总表。

框架适配前使用模块fixture和受控service-response文件完成draft→finalize代表路径，不伪造主框架已经具备页面或管理进程。

C3结束时必须形成：

- 模块私有配置、历史索引、经验目录、AI请求和AI结果Schema；
- 独立AI报告模块测试；
- FCR可直接采用的输入/输出示例；
- 适配前测试证据和明确阻塞；
- 更新后的 `00-context-handoff.md` 和开发总日志。

## 5. 主框架适配等待点和最小范围

本期只请求一个“AI汇总报告”入口，不请求完整三功能首页、规则管理页面或候选规则页面。

框架需要提供：

1. 选择当前汇总表；
2. 导入/多选历史数据；
3. 多选approved经验；
4. 输入分析问题；
5. 展示模块生成的脱敏预览并逐次取得联网同意；
6. 使用现有Provider和service response流程；
7. 展示并打开独立Markdown/JSON成果；
8. 提供moisture模块数据目录和最小只读目录查询/历史导入进程宿主。

框架不得解析水分Excel、筛选经验scope、生成趋势、修改规则颜色或重新组织AI业务结果。

对应请求：[`../framework-change-requests/FCR-moisture-20260723-ai-report-context-selection.md`](../framework-change-requests/FCR-moisture-20260723-ai-report-context-selection.md)。

模块完成C3后暂停跨边界联调，等待框架负责人审核FCR。框架方应在独立分支完成适配并合入 `integration`；模块方不得直接修改框架代码。

框架适配完成的最低信号为：

- FCR写入明确审核结论和实施PR；
- 页面能够创建 `ai_report` 操作；
- 模块数据目录和窄化管理进程调用方式已冻结；
- TaskService能够完成脱敏预览、逐次同意和service response回传；
- 结果中心能够展示独立Markdown/JSON；
- integration相关框架测试通过。

## 6. 主框架适配后：真实联调与交付

### C4（Codex）：同步integration与接口差异审计

- 确认工作区干净后合并最新 `integration`；
- 只在 `modules/moisture/` 解决模块适配问题；
- 对照FCR审核结果检查私有配置、管理进程和成果展示接口；
- 若框架实际接口偏离已批准FCR，停止并记录，不用模块绕过框架缺口。

### S4（Claude Code＋DeepSeek）：清晰适配项和回归fixture

在Codex冻结差异清单后，S4只处理模块侧机械适配、fixture、局部合同测试和文档示例。不得改框架，也不得改变C2/C3的隐私、ID和降级语义。

### C5（Codex）：真实主框架闭环

通过真实Registry、Runner和TaskService验证：

```text
选择当前表/历史/经验/问题
→ 创建独立draft
→ 模块声明AI请求
→ 框架脱敏预览和逐次同意
→ Provider或结构化降级
→ 独立finalize
→ 展示Markdown/JSON
```

同时验证draft/finalize为独立进程、request ID稳定、原汇总表SHA-256不变、普通summary不调用AI、AI失败不破坏四表成果。

### S5（Claude Code＋DeepSeek）：版本、文档和脱敏证据

在C5通过后，S5按冻结清单更新v1.0.1版本元数据、CHANGELOG、README、三份指导文档、脱敏样本和测试证据。不得提前把未验收能力写成已完成。

### C6（Codex）：最终门禁和交付审查

- 运行合同、模块测试、Ruff、version、self-check；
- 构建便携运行时并验证summary与AI报告draft→finalize；
- 人工对照四表关键值和AI报告；
- 审计修改范围、敏感数据、FCR状态和回滚提交；
- 形成提交号、Draft PR、测试结果、人工对照和已知限制。

## 7. 明确延期

以下能力不进入v1.0.1本期实现或本期FCR：

- 历史汇总表追加新原始数据；
- AI候选规则生成；
- 规则草稿、发布、停用和恢复页面；
- 任务规则快照和新的active binding；
- 经验编辑UI；
- 数据库、多人审批、角色权限和在线协作；
- 全量历史回放、混淆矩阵和自动阈值推荐。

它们继续保留在总体下一阶段架构中，后续按独立版本和独立FCR逐项实施。

## 8. 测试与验收

### 模块定向测试

- 新汇总工作簿恰好包含四张固定工作表；
- “模型分析记录”不存在，其他四表关键值、排序、格式和图表不变；
- 普通summary draft不声明AI复判请求；
- 普通summary finalize不读取AI响应，不产生红蓝提升；
- v1.0.0五表工作簿可只读导入历史资料库；
- v1.0.1四表工作簿可导入且重复SHA被拒绝或跳过；
- draft/retired经验无法被选择，approved经验引用可追溯；
- 相同AI分析输入产生相同request ID和上下文哈希；
- payload不含完整Excel、绝对路径、原始行和未授权身份；
- 合法响应生成独立Markdown/JSON且不修改汇总表SHA-256；
- denied、error、timeout和非法响应全部安全降级；
- 历史索引和报告原子写失败不损坏旧文件。

### 交付门禁

所有Python命令显式使用仓库 `.venv`：

```powershell
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable); print(sys.version)"
.\.venv\Scripts\python.exe -m pytest --version
.\.venv\Scripts\python.exe -m app.tools.module_contract_cli validate modules/moisture
.\.venv\Scripts\python.exe -m pytest modules\moisture\tests -q
.\.venv\Scripts\python.exe -m ruff check modules\moisture
modules\moisture\run_module.bat version
modules\moisture\run_module.bat self-check
```

最后完成源码和便携运行时的summary及独立AI报告draft→finalize代表路径。不得用全仓测试替代模块业务验收。

## 9. 版本、证据和交付

实现完成后统一把模块活动版本元数据从 `1.0.0` 更新到 `1.0.1`，不得使用 `1.1.0`。

同时更新：

- `CHANGELOG.md`；
- 四表和独立AI报告测试；
- 脱敏当前汇总表、历史汇总表、approved经验和AI响应样本；
- `docs/evidence/`中的测试命令、结果、人工对照和输入SHA-256；
- README及三份当前指导文档。

最终只提交 `modules/moisture/`，更新 `module/moisture → integration` Draft PR，不指向main、不自行合并。交付记录必须包含提交号、Draft PR、测试结果、四表人工对照、AI报告截图或文本对照、输入完整性和回滚提交。
