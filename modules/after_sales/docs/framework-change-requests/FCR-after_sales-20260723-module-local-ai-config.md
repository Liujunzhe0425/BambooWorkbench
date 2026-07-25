---
request_id: FCR-after_sales-20260723-module-local-ai-config
module_id: after_sales
module_version: 1.1.1
owner: 售后分析模块负责人
status: superseded
framework_areas:
  - ui
  - storage
  - workflow
breaking_change: false
required_before_module_merge: false
---

# 已废止：售后模块页专属 AI 配置与模块本地直连

本请求提出的“模块读取 Windows 凭据并自行调用外部 Provider”方案违反当前框架的凭据、授权、
脱敏、审计和故障隔离边界，因此不再申请实施，也不得作为模块代码的启用依据。

替代请求为：

`FCR-after_sales-20260725-framework-ai-adapter.md`

新请求保留售后任务页一次启动、先 AI 后人工复核的业务体验，但由主框架托管 API Key 和外部
HTTP 调用。售后模块只生成脱敏请求并消费结构化响应。

本历史请求中的案例、文件名、金额和业务特征已删除。共享 Git 历史是否需要进一步清理由项目
负责人决定；模块负责人不得自行重写历史。
