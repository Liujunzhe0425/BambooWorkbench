---
request_id: FCR-after_sales-20260722-ai-preanalysis-review
module_id: after_sales
module_version: 1.5.0
owner: 售后分析模块负责人
status: superseded
framework_areas:
  - workflow
  - service
  - ui
breaking_change: false
required_before_module_merge: false
---

# 框架适配请求：AI 预分析完成后再进入逐文件人工复核

> 本请求已被 `FCR-after_sales-20260723-module-local-ai-config.md` 取代。新请求采用售后模块页一次配置与一次显式启动授权，避免生成逐请求“允许/拒绝”确认项。

## 1. 业务目标与使用场景

售后人员一次选择 1 至 100 份售后 Excel。模块先确定性读取“反馈内容、方案申请明细、售后负责人调查情况、售后解决方案、责任落实”等原文，再由用户授权的 DeepSeek 或 OpenAI 兼容服务逐份给出品牌、售后根因、投诉类型、责任工厂、费用候选和解决状态建议。AI 返回且经模块完整性校验后，用户必须按每份文件复核售后费用、责任工厂和投诉类型，最后才生成正式汇总表。

AI 只提供建议。确定性费用规则和人工复核高于模型结果；任一 AI 响应失败不得导致输入文件丢失。

## 2. 当前限制

现有任务合同仅有 `draft`、`finalize` 两个阶段：

- `contracts/schemas/job-request.schema.json` 的 `JobPhase` 只有上述两个值；
- `core/tasks/service.py::_begin_finalize` 在用户提交当前确认表后执行 `service_requests`，随后直接运行 `finalize`；
- `core/tasks/service.py::_finished` 只对 `draft` 调用 `_prepare_pending_result`，`finalize` 返回的新确认项不会再次进入待确认；
- `core/tasks/service.py::_service_consent_prompts` 把每个 AI 请求分别生成不可批量应用的确认项。

因此当前顺序是“离线建议人工复核 + AI 联网授权 → 调用 AI → 直接结束”。人工复核时看不到 AI 结果，无法实现正确的“AI 分析 → 人工复核 → 正式导出”顺序。若 100 份文件按字节预算拆成多个请求，用户还需要重复确认多次联网授权。

## 3. 请求的框架改动

### 3.1 页面与交互

- 页面/区域：任务创建页和待确认页沿用现有入口；待确认页增加明确的“AI 联网授权阶段”和“售后业务复核阶段”状态。
- 按钮/控件：一批任务只显示一次“允许本批次使用已选 AI 服务/拒绝”授权；业务复核仍按文件一行显示售后费用、责任工厂、投诉类型。
- 用户操作顺序：选择文件 → 查看脱敏预览并授权 → 显示 AI 分析进度 → 展示逐文件 AI 建议和证据 → 逐文件人工复核 → 生成正式结果。
- 输入与校验：AI 失败或用户拒绝时仍进入业务复核，展示“已使用离线结果”状态；阻断字段按售后模块确认合同校验。
- 加载、空状态、错误状态：显示已完成文件数、AI 批次总数、失败批次及降级文件数；不显示 API Key。
- 结果展示：每份输入文件保持独立条目，显示 AI/离线来源、短证据和需要人工确认的三个字段。

### 3.2 接口与合同

- 当前输入/输出：草稿 `result.json` 声明 `service_requests`，用户提交一次确认后框架执行服务并直接创建 `finalize` 任务。
- 期望输入/输出：框架执行服务后允许模块进行一次“预分析结果绑定”运行，并把该运行返回的业务 `confirmations` 继续交给用户；业务确认完成后再运行最终导出。
- 新增或修改字段：优先由框架内部状态机表达，不要求旧模块使用新字段。若必须扩展合同，建议新增向后兼容的可选阶段或 `workflow_step`，并同步统一 schema、Pydantic 模型和示例。
- 结构化输出：AI 请求 payload 可选声明 `response_format={"type":"json_object"}` 和输出令牌上限；DeepSeek/OpenAI 兼容 Provider 在支持时传递该选项，不支持时保持现有提示词降级。模块仍负责严格 JSON 校验，不能因为启用 JSON 模式而信任未校验结果。
- 状态变化建议：`running_draft → waiting_service_consent → running_services → running_review_draft → waiting_business_confirmation → running_finalize → success/partial_success`。
- 旧模块兼容方式：未声明 AI 预分析工作流的模块继续使用现有 draft/finalize；水分、煮沸模块行为不得改变。

服务响应继续使用现有 `service-response.json` 信封。模块以 `request_id`、`batch_id`、`case_id` 三层身份校验，要求每个请求恰好覆盖其全部输入案件。

### 3.3 公共服务、存储或打包

- 所需能力：复用 `ServiceOrchestrator`、DeepSeek/OpenAI 兼容 Provider、安全凭据存储、脱敏预览和同意审计；新增同一任务的多阶段编排和本批次统一授权。
- 调用时机：只在用户明确授权后；API Key 永不传给业务模块。
- 数据保存位置：仅保存在任务目录内的服务协议文件和审计数据库；模块收到的仍是任务本地 `service_response_file`。
- 安装版/便携版要求：不得依赖开发机 `.venv`、系统 Python 或 C 盘临时目录；运行数据继续使用工作台配置的 D 盘数据目录。
- 无服务或失败时的降级行为：保留所有文件的离线记录，标记失败原因并进入人工复核；不得把费用未知改为 0，不得跳过文件。

## 4. 责任边界

- 模块方已经完成：按固定字节预算构造脱敏 AI 请求；每个输入文件使用稳定 `case_id`；严格验证响应信封、请求、批次、案件覆盖、枚举、金额和证据；API 失败逐文件降级；AI 结果应用后仍保留人工复核为最终值。
- 等待框架提供：AI 服务完成后再次进入业务确认的工作流；一批任务一次联网授权；相应状态和页面提示。
- 仍由模块方负责的业务逻辑：品牌不等于客户、日期口径、性能/外观/加工分类、费用确定性规则、责任工厂候选、解决状态、100 文件完整性对账、Excel 和报告正确性。
- 需要人工确认的结论：每份文件的售后费用、责任工厂、投诉类型；低置信度或缺失的品牌、日期等现有复核项。

## 5. 数据、安全与权限

模块只发送分析所需的产品、反馈、申请、调查、方案和责任文本，不发送 Excel 二进制、完整本地路径、客户字段、销售人员字段或 API Key。模块在构造请求时先替换手机号、邮箱和本地路径，框架仍需执行统一脱敏并展示联网预览。用户拒绝后不得联网。

DeepSeek 配置由工作台系统设置和 Windows 安全凭据存储管理。模块不读取环境变量中的统一工作台密钥，不把密钥写入日志、结果、安装包或 Git 仓库。

## 6. 兼容性与迁移

- 是否破坏现有合同：否（首选内部工作流扩展；如需合同字段必须保持可选和向后兼容）。
- 是否兼容当前正式版模块：是；未启用新工作流时模块仍能离线分析、人工复核和导出。
- 旧任务和历史数据如何处理：按旧流程打开和导出，不自动重跑 AI。
- 如果框架尚未升级，模块能否继续运行：能，但人工复核页面只能看到离线建议；AI 响应仅用于最终分析补充，页面需明确此限制。
- 回滚方式：关闭售后 AI 预分析能力，恢复现有 draft/finalize 路径；不需要迁移业务 Excel。

## 7. 验收标准

1. 给定 5 份脱敏售后 Excel，用户授权 DeepSeek 后，系统先完成 AI 响应，再展示 5 条逐文件业务复核行；每行至少有售后费用、责任工厂、投诉类型和来源证据。
2. 用户修改任一 AI 建议并提交，最终 `after_sales_records.json`、全量汇总 Excel、年度统计 Excel 和分析报告均使用人工值。
3. 给定 100 份 Excel，AI 请求按预算拆分，100 个 `case_id` 恰好出现一次；任意一个请求超时只降级该请求对应文件，其余文件继续分析，最终对账仍为 100。
4. AI 返回缺失、重复或未知 `case_id` 时，模块拒绝该请求的整批结果并进入人工复核，不丢文件、不把未知费用写为 0。
5. 用户拒绝联网时没有外部请求，全部文件以离线建议进入业务复核并可完成导出。
6. API Key 不出现在任务目录、日志、结果 JSON、Excel、安装包和 Git 变更中。
7. DeepSeek 和 OpenAI 兼容 Provider 均通过同一模块请求工作；切换 Provider 不需要修改售后模块。
8. 水分和煮沸模块现有 draft → finalize 测试全部通过。
9. Windows 便携版在未安装系统 Python、没有开发机 `.venv` 的环境中完成上述流程，运行数据写入用户配置的 D 盘目录。

## 8. 备选方案与影响

- 已考虑的替代方案：模块直接调用 DeepSeek；在现有同一确认页同时展示离线业务确认和 AI 授权；AI 请求设置为无需同意；把 100 份内容塞入单次请求。
- 未采用原因：直接调用会绕过密钥托管、脱敏和审计；同页顺序导致人工看不到 AI 建议；跳过同意不符合安全边界；单次大请求容易超过上下文或输出限制且难以隔离失败。
- 影响的框架目录/功能：预计为 `core/tasks/`、任务状态模型、待确认页和相应测试；是否需要合同变化由框架方评估。
- 影响的其他模块：默认不影响；新工作流必须由模块显式声明。
- 预计风险：任务恢复、崩溃重入、多阶段协议身份绑定和历史任务兼容，需要补充状态机与集成测试。

## 9. 附件与证据

- 脱敏样本：`modules/after_sales/tests/fixtures/samples/input/sample_after_sales.xlsx`
- 模块侧 AI 请求与响应测试：`modules/after_sales/tests/test_ai_service.py`
- 业务复核测试：`modules/after_sales/tests/test_contract_adapter.py`
- 相关现有请求：`modules/after_sales/docs/framework-change-requests/FCR-after_sales-20260721-confirmation-file-rows.md`

## 10. 框架方审核（由框架负责人/Codex填写）

- 审核结论：待审核
- 判断理由：
- 实施分支/PR：
- 验证范围：
- 对模块交付的后续要求：
