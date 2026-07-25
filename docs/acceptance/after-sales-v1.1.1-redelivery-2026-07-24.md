# 售后模块 v1.1.1 整改与重新交付说明

对象：远端分支 `module/after-sales`，已验收提交 `1ffab60`；当前没有对应的新 PR。

## 当前问题、位置和原因

分支推送成功且模块测试通过，但交付不符合框架和安全边界：

1. 没有创建 `module/after-sales -> integration` 的新 PR。
2. `module.json` 和 CLI 报告 `1.6.4`，违反当前统一 `1.1.1` 版本线。
3. `FCR-after_sales-20260723-module-local-ai-config.md` 标记
   `required_before_module_merge: true`，但仍为 `proposed`，框架没有批准或实现专属配置页。
4. `module_ai_config.py` 通过 `keyring` 直接读取 API Key，模块进程直接调用外部模型，绕过
   框架统一 AI Provider、凭据管理、审计和 `service_requests` 人工授权合同。
5. manifest 仍写 `requires_network: false`，与上述可联网执行路径不一致。
6. FCR 包含带人名的真实样表文件名、具体金额和案件特征，违反不得提交客户数据的边界。
7. 本轮改变了既有输出集合和文件名；这些业务输出是否符合客户预期必须由售后负责人确认，
   框架负责人不代签。

## 责任边界和整改决策

模块负责人负责售后解析、业务字段、输出和模块侧 AI 请求内容；框架负责人负责统一 Provider、
凭据、人工授权、TaskService/Runner 和公共 UI。模块不得因为认为公共交互不理想，就自行读取
工作台凭据或建立第二套联网通道。

重新交付前必须选择以下路径，并在 PR 中明确：

- 推荐路径：恢复并适配现有统一 `service_requests`/Provider 流程，模块只生成脱敏请求并消费
  框架响应，不读取 API Key、不直接联网；如需改善页面，将 FCR 限定为框架 UI 优化且不作为
  模块合并前置。
- 若坚持专属 AI 配置与一次启动授权：保持 FCR 为合并前置，等待项目负责人明确批准该产品
  交互及框架独立实现完成；在此之前模块 PR 不得合并。

不得由模块负责人自行把第二条路径视为已批准。

## 必须达到的目标和验收标准

- 删除仓库中的客户姓名、真实文件名、具体案件信息，改用完全虚构脱敏样例；必要时确认 Git
  历史是否需要进一步清理，但不得自行重写共享分支历史；
- 模块版本统一为 `1.1.1`；manifest 的能力与真实行为一致；
- 默认与自检绝不读取凭据或联网；正式联网只能经过获批的框架合同；
- API Key 不进入任务、SQLite、输出、日志、异常、安装包或 Git；
- draft -> 人工确认 -> finalize 保持可运行，finalize 不重复调用 AI；
- 源码和便携入口均通过，失败时不丢输入并安全降级；
- 对改变的输出集合，由售后负责人提交业务验收说明和脱敏预期结果；
- 完整 pytest、Ruff、合同、version、self-check、真实 TaskService 流程和 `git diff --check`
  通过。

## 修改范围、重新交付和禁止事项

只修改 `modules/after_sales/`。创建新的 Draft PR：`module/after-sales -> integration`，不得指向
`main`。禁止修改框架目录、其他模块、`integration`/`main`；禁止提交真实客户文件、姓名、
路径、密钥、接口响应、缓存或运行产物；禁止把 API Key 写进任务 JSON 或环境持久化。

完成后提供 PR 编号/链接、最新完整 SHA、版本 `1.1.1`、采用的 AI 合同路径、改动摘要、业务
输出自测签字、完整测试结果和重点复验接口。

## 给售后负责人的人类通知

你的 `1ffab60` 已成功推送，模块 50 项测试通过（3 项按设计跳过），但当前没有新 PR；版本
1.6.4 不符合统一 1.1.1，专属 AI 配置 FCR 尚未获批且代码直接读取凭据联网，仓库文档还含
客户姓名样表信息，因此不能合并。请按本文选择统一 Provider 路径或等待 FCR 获批，完成脱敏、
版本统一和业务输出签字后，新建指向 integration 的 Draft PR。

## 给售后负责人 AI Agent 的执行提示词

```text
在 BambooWorkbench 的 module/after-sales 分支整改最新提交。先同步最新 integration，修改范围
严格限定 modules/after_sales/。当前默认采用推荐方案：模块不得用 keyring 读取工作台 API Key，
不得直接联网；恢复/适配统一 service_requests + 框架 Provider 流程，保留失败降级、逐文件人工
复核和 finalize 不重复调用 AI。若用户明确批准专属 AI FCR，则先停止模块合并并等待框架独立
实现，不能自行假定批准。删除 FCR 中真实姓名样表文件名、金额和案件特征，改用虚构脱敏样例；
不要重写共享历史。将模块公开版本统一为 1.1.1，核对 manifest 能力与 requires_network。
为输出集合变更补业务自测证据。运行完整 pytest、Ruff、合同、version、self-check、真实
TaskService draft/finalize、git diff --check。创建新的 Draft PR，方向只能是
module/after-sales -> integration。完成后报告 PR、完整 SHA、版本、AI 合同选择、业务签字、
测试结果和重点复验接口。不得修改框架、其他模块、integration 或 main，不得提交客户数据、
密钥、真实路径、缓存、日志或接口响应。
```
