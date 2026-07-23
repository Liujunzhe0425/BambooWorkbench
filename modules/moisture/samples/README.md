# 合成与脱敏样本

本目录只保存模块合同、draft/finalize 和 service request/response 的合成或脱敏示例，
不保存客户原始工作簿、真实供应商身份、绝对路径、凭据或运行日志。

- `jobs/`：普通 draft/finalize 与独立 AI 报告配置/JobRequest 示例；`${...}` 占位符必须由宿主替换为任务绝对路径。
- `protocol/`：确认答案以及 v1.0.1 独立 AI 报告请求、合法响应和拒绝响应示例。

AI 示例仅包含合成统计和占位哈希，不包含完整 Excel、原始行、绝对路径、真实供应商身份或凭据。

业务验收用 Excel 由测试 fixture 在运行时生成，不作为客户原始数据提交。
