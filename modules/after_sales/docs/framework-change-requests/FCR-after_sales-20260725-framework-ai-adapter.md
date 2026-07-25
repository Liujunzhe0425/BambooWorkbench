---
request_id: FCR-after_sales-20260725-framework-ai-adapter
module_id: after_sales
module_version: 1.1.1
owner: 售后分析模块负责人
status: implemented
framework_pr: 58
framework_merge: a7b66f95ec3fa535501c43bc1f4548135a5baa45
breaking_change: false
required_before_module_merge: false
---

# 售后强制 AI 接入页与框架托管调用适配器

## 结论

框架 PR #58 已合入 `integration`。框架提供售后模块专用 AI 接入页、连接测试、本批次授权、Provider 托管调用和 `service_before_confirmation` 编排。售后模块已按正式合同完成接线，不再建立模块凭据或外部 HTTP 通道。

## 正式合同

```json
{
  "requires_network": false,
  "framework_ai": {
    "required": true,
    "setup_page": "module",
    "service_before_confirmation": true
  }
}
```

`requires_network: false` 描述模块进程自身的网络边界。`framework_ai.required: true` 描述标准售后任务必须先经框架 AI 门禁和 Provider 服务。真实 API Key 只存在于框架凭据服务，不能传给模块。

## 工作流

```text
售后 AI 接入页配置与连接测试
-> 本批次授权
-> 第一次 draft 生成脱敏 service_requests
-> 框架 Provider 调用并写 service-response.json
-> 第二次 draft 校验并绑定 AI 候选
-> 逐文件人工确认费用、责任工厂和投诉类型
-> finalize 复用响应和人工答案生成正式成果
```

第一次 draft 不生成业务确认。第二次 draft 不再申请服务。finalize 的服务请求数必须为 0，重复 finalize 由框架任务状态机拒绝。

## 模块责任

- 解析全部输入并为每个成功案件生成稳定案件 ID。
- 对业务文本进行二次脱敏、限长和分批。
- 校验响应信封、请求 ID、批次 ID、案件 ID、字段类型和受控枚举。
- 把 AI 结果作为候选绑定，保留人工确认的最终权限。
- 对拒绝、超时、服务错误、缺失和非法响应逐批降级，不丢失输入。
- finalize 只消费已存在的响应和确认文件。

## 框架责任

- 展示售后 AI 配置页并在配置、连接测试或本批次授权未完成时阻止任务创建。
- 托管 Provider、模型选择、API Key、网络请求、脱敏预览和授权审计。
- 将服务响应写入任务本地 `protocol/service-response.json` 并触发第二次 draft。
- 将同一响应文件传给 finalize，不重复调用 Provider。

## 安全边界

- 模块源码、依赖和便携构建均不包含凭据库客户端或 Provider HTTP 网关。
- API Key 不进入任务 JSON、模块配置、SQLite、输出、日志、异常、安装包或 Git。
- 请求不发送客户身份、联系人、销售、电话、邮箱、地址、订单号、本机路径、原文件名或工作簿二进制。
- AI 不得直接决定售后费用、责任工厂、责任认定、赔偿、审批或结案状态。
- 默认自检和测试不读取凭据、不联网。

## 验收覆盖

- 成功响应绑定及人工确认写回。
- 分块部分失败，仅降级受影响案件。
- 任务开始前拒绝授权，不创建任务且 Provider 调用为 0。
- 拒绝、超时、服务错误和非法 JSON 保留完整离线结果。
- 真实 `TaskService` 两次 draft 后 Provider 调用一次，finalize 前后调用数不变。
- 重复 finalize 被拒绝。
- 源码入口和便携入口完成 draft、降级、人工确认及 finalize。

## 删除项

- 模块本地凭据配置读取器及其测试。
- 模块本地 Provider HTTP 网关及其测试。
- 提取器中的直连分析入口和运行时开关。
- `keyring` 运行依赖及 PyInstaller 收集项。

旧售后专属凭据不迁移、不读取。历史 Git 不由模块分支重写；如需清理既有远端历史，由项目负责人单独决策。
