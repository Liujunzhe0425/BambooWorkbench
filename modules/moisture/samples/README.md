# 合成与脱敏样本

本目录只保存模块合同、draft/finalize 和 service request/response 的合成或脱敏示例，
不保存客户原始工作簿、真实供应商身份、绝对路径、凭据或运行日志。

- `jobs/`：draft 与 finalize 的 JobRequest 示例；其中 `${...}` 占位符必须由宿主替换为任务绝对路径。
- `protocol/`：确认答案以及 AI 合法、拒绝响应示例。

业务验收用 Excel 由测试 fixture 在运行时生成，不作为客户原始数据提交。
