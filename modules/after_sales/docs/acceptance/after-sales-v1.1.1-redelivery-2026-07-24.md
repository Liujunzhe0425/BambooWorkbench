# 售后分析模块 v1.1.1 整改与重新交付验收文档

日期：2026-07-24  
分支：`module/after-sales`  
模块版本：`1.1.1`  
目标：`module/after-sales → integration` Draft PR  
AI 接入目标：**统一 service_requests + 框架 AI Provider**（等待框架适配）

> 状态更正（2026-07-25）：本文件原先把目标方案误写成已完成。当前 CLI 仍保留模块 keyring
> 读取和 Provider 直连路径，不能按现状合入 `integration`。实际状态和后续边界以
> `FCR-after_sales-20260725-framework-ai-adapter.md` 为准。

---

## 1. 整改背景

根据框架验收结果，原提交 `1ffab604d04d9c9d535c91ed4b5dbe084c490376` 存在以下问题需要整改：

- 版本号错误（1.6.4 → 1.1.1）
- Git 合并冲突未完全解决
- 模块内包含直连 API 网关和凭据读取代码（`deepseek_gateway.py`、`llm_analyzer.py`）
- FCR 标记 `required_before_module_merge: true`，不得作为合并前置
- module.json 声明与模块实际行为不一致
- 文档和样例中包含客户数据

---

## 2. 整改清单与完成状态

### 2.1 版本统一 → 1.1.1

| 文件 | 修改内容 |
|---|---|
| `module.json` | `module_version` 改为 `1.1.1`；联网声明仍待适配后与完整行为统一 |
| `src/after_sales_agent/__init__.py` | `MODULE_VERSION` 改为 `1.1.1` |
| `README.md` | 标题改为 `1.1.1` |
| `CHANGELOG.md` | 新增 `1.1.1` 条目 |
| `tests/test_self_check.py` | 版本断言改为 `1.1.1` |
| `scripts/verify_portable_draft_finalize.py` | 版本断言改为 `1.1.1` |

### 2.2 AI 接入方案 → 等待框架适配

模块内部：

- `deepseek_gateway.py`、`llm_analyzer.py`：当前仍构成模块本地 Provider 调用链。
- `module_ai_config.py`：当前仍包含 Windows keyring 读取逻辑。
- `cli.py`：当前仍导入 `module_ai_config`，并可在特定开关下启用模块本地 AI。
- `ai_service.py`：已有统一 AI 请求/响应/降级辅助函数，但尚未完整接入 CLI 的 draft/finalize。
- 结论：目标方案尚未完成；当前 PR 必须保持 Draft，等待框架先通过独立 PR 提供适配器。

### 2.3 FCR 标记修正

- `FCR-after_sales-20260721-confirmation-file-rows.md`：`required_before_module_merge` 改为 `false`
- `FCR-after_sales-20260722-ai-preanalysis-review.md`：`required_before_module_merge` 保持 `false`（已正确）
- `FCR-after_sales-20260725-framework-ai-adapter.md`：`required_before_module_merge: true`，为当前有效请求

### 2.4 客户信息清理

| 位置 | 清理情况 |
|---|---|
| 文档中的真实姓名 | 已确认无真实姓名（测试中的"张三"为脱敏测试数据） |
| 真实样表文件名 | 已确认所有样本均为虚构文件名 |
| 具体金额和案件特征 | 已确认测试数据均为虚构 |
| `__pycache__/` *.pyc 文件 | 已全部删除 |

### 2.5 module.json 声明修正

```json
{
  "module_version": "1.1.1",
  "requires_network": false
}
```

- `requires_network: false`：只符合默认离线路径；当前保留的可选直连代码使清单与完整行为仍不一致
- `capabilities`：当前不声明未定义或未实现的可选能力；输入格式和批量能力使用清单已有字段

### 2.6 默认运行安全

- `self-check`：生成内存工作簿，不读取凭据，不联网
- 测试：所有测试使用虚构数据，不联网
- CLI 默认 draft/finalize：未设置专用环境开关时不读取凭据、不联网；直连代码仍待适配后删除

---

## 3. 2026-07-25 基线复验结果

| 检查项 | 命令 | 实测结果 |
|---|---|---|
| 单元测试 | `python -m pytest modules/after_sales/tests -q` | `50 passed, 3 skipped` |
| Ruff | `python -m ruff check modules/after_sales` | 通过 |
| 静态合同 | `python -m app.tools.module_contract_cli validate modules/after_sales` | 通过 |
| 版本 | `modules\after_sales\run_module.bat version` | `after_sales 1.1.1` |
| 自检 | `modules\after_sales\run_module.bat self-check` | 通过 |
| 真实 TaskService 离线闭环 | 真实模块 draft → 3 项人工确认 → finalize | `success`，登记 6 个输出 |

真实 TaskService 基线同时确认：draft 的 `service_requests` 数量为 0，finalize 的
`service_response_file` 为 `null`。这证明当前离线业务闭环可运行，但也证明统一 AI 服务接线尚未
完成，不能作为 FCR 已实现或模块可合并的证据。

---

## 4. 业务输出变更

本版本无新增或删除业务输出文件。所有输出维持不变：

- `after_sales_annual_rollup.xlsx`
- `after_sales_summary.xlsx`
- `after_sales_records.json`
- `after_sales_analysis.md`
- `after_sales_analysis_report.docx`
- `after_sales_brand_share.xlsx`
- `after_sales_reason_share.xlsx`
- `after_sales_monthly_fee.xlsx`
- `after_sales_yearly_dashboard.xlsx`
- `result.json`

---

## 5. draft → finalize 验证

| 流程 | 验证结果 |
|---|---|
| draft 阶段生成 service_requests | 当前 CLI 未完成接线，待框架适配后复验 |
| AI 拒绝后离线降级 | 辅助函数已有覆盖，完整 TaskService 流程待复验 |
| 人工复核三项必审字段写回 | ✓ |
| finalize 不重复调用 AI | 当前本地快照路径已有测试，框架响应流程待复验 |
| finalize 网络调用次数为 0 | 必须在框架适配后的真实 TaskService 流程复验 |

---

## 6. 需要框架重点复验的接口

1. **service_requests**：draft 阶段的 `result.json` 中 `service_requests` 字段结构与合同一致性
2. **service_response_file**：finalize 阶段的响应信封解析、身份校验和降级路径
3. **人工复核三项**：售后费用、责任工厂、投诉类型三项阻断确认的正确生成和写回
4. **confirmation_file 写回**：人工确认值在最终 Excel、JSON、图表和报告中的一致性
5. **module.json 合同**：不声明未实现能力，`requires_network` 与模块自身行为一致
6. **自检不联网**：默认 `self-check` 和测试不应读取凭据或发起网络请求

---

## 7. 回滚

- PR 合并前：关闭 Draft PR，分支不受影响
- PR 合并后：回滚 PR 合并提交
- 回滚基线：`integration` 最新提交
