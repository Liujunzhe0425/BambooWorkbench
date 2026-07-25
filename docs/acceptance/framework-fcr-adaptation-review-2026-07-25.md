# 水分与售后 FCR 框架适配审核记录（2026-07-25）

审核对象：

- 水分 PR #52：`FCR-moisture-20260724-public-management-contract`；
- 售后 PR #57：`FCR-after_sales-20260725-framework-ai-adapter`；
- 框架实施分支：`agent/framework-governance-after-sales-ai`。

## 审核结论

两项请求的核心方向均批准。框架不导入模块内部 Python service/repository，模块进程也不得
读取框架凭据或直接调用外部 Provider。

水分统一管理合同按提案实施：manifest 增加可选 `management_contract` 描述符，Registry
约束模块内 Schema 路径，框架和模块分别进行请求/响应校验；TaskService 在创建水分任务前
通过管理进程查询当前规则身份，并把同一 `{version, sha256}` 固定到 draft/finalize 的模块
配置中。经验和规则管理通过统一管理进程页面调用，不直接引用模块实现。

售后强制 AI 接入方向批准，但对 manifest 语义作一项修正：`requires_network` 继续只表示模块
进程自身联网。售后模块接入后仍应保持 `requires_network: false`，另用可选 `framework_ai`
描述符声明“框架托管 AI 必需、模块专属配置页、AI 服务先于业务确认”。这样既能强制正式
售后流程使用框架 Provider，又不会错误授予模块进程网络或密钥权限。

## 框架实现

### 水分

- 新增 `management_contract={schema_version, request_schema, response_schema}`；
- 拒绝绝对路径、`..` 越界、符号链接、不存在或无效 JSON Schema；
- 通用 Management Runner 支持模块自有版本化请求/响应并校验身份；
- ManagementService 提供异步 UI 操作和受控同步查询；
- 新增经验/规则三栏视图和通用公开操作区；
- TaskService 创建水分任务时查询 `get_active_rule_identity`；
- 规则快照写入模块配置，finalize 沿用原配置且不重新查询。

### 售后

- 新增 `framework_ai={required, setup_page, service_before_confirmation}`；
- 点击售后模块后先进入专用 AI 接入页；
- 页面支持 Provider、HTTPS Base URL、模型、API Key、凭据掩码和连接测试；
- API Key 只进入框架 CredentialStore，不写 SQLite、任务或模块配置；
- 未通过连接测试不能进入文件选择；
- 文件页要求本批次明确授权，未授权不能创建任务；
- 第一次 draft 只接收脱敏 service requests；
- 框架执行 Provider 后，将 service-response 注入第二次 draft；
- 第二次 draft 生成 AI 已绑定的逐文件业务确认；
- finalize 复用同一 response，不再次调用 Provider；
- Provider 错误继续以结构化响应交给模块降级，不丢失任务输入。

## 模块后续最小提交

水分负责人需要在框架 PR 合入后同步 `integration`，在 `module.json` 增加：

```json
"management_contract": {
  "schema_version": "1.1",
  "request_schema": "schemas/moisture-management-request.schema.json",
  "response_schema": "schemas/moisture-management-response.schema.json"
}
```

除此之外不得重写已通过验收的管理业务实现。

售后负责人需要在框架 PR 合入后同步 `integration`，在 `module.json` 增加：

```json
"framework_ai": {
  "required": true,
  "setup_page": "module",
  "service_before_confirmation": true
}
```

同时保持 `requires_network: false`，把 `ai_service.py` 接到两次 draft/finalize，删除模块
keyring、环境开关、直联网关和相关打包依赖，废止旧的本地 AI 配置 FCR。每个成功解析文件
必须进入 AI 请求；第二次 draft 必须在 AI 成功或明确失败后产生逐文件人工确认。

## 发布门禁

框架适配完成不等于三个模块已经可发布。PR #52、#54、#57 仍保持 Draft；水分和售后完成
上述最小兼容提交后，框架重新 fetch 并只复验新增接口。三个模块全部通过后才能合入
`integration`、执行组合验收、更新正式版本和发布 Release。
