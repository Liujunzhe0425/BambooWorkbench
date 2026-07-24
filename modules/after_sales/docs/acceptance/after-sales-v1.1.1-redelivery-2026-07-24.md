# 售后分析模块 v1.1.1 整改与重新交付验收文档

日期：2026-07-24  
分支：`module/after-sales`  
模块版本：`1.1.1`  
目标：`module/after-sales → integration` Draft PR  
AI 接入方案：**统一 service_requests + 框架 AI Provider**（推荐方案）

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
| `module.json` | `module_version` 改为 `1.1.1`，增加 `capabilities` |
| `src/after_sales_agent/__init__.py` | `MODULE_VERSION` 改为 `1.1.1` |
| `README.md` | 标题改为 `1.1.1` |
| `CHANGELOG.md` | 新增 `1.1.1` 条目 |
| `tests/test_self_check.py` | 版本断言改为 `1.1.1` |
| `scripts/verify_portable_draft_finalize.py` | 版本断言改为 `1.1.1` |

### 2.2 AI 接入方案 → 统一 service_requests（推荐方案）

模块内部：

- `deepseek_gateway.py`：模块**保留**仅供结构化测试使用，CLI 入口不调用。
- `llm_analyzer.py`：模块**保留**仅供结构化测试使用，CLI 入口不调用。
- `ai_service.py`：完整的统一 AI 请求/响应/降级/校验代码**保持完备**。
- CLI 主入口 `cli.py`：不导入 `deepseek_gateway`、不导入 `llm_analyzer`、不读取 API Key。
- 模块只生成脱敏 service_requests，由工作台统一授权和执行。
- API Key 由框架凭据管理，不进入任务 JSON、SQLite、输出、日志、安装包或 Git。

### 2.3 FCR 标记修正

- `FCR-after_sales-20260721-confirmation-file-rows.md`：`required_before_module_merge` 改为 `false`
- `FCR-after_sales-20260722-ai-preanalysis-review.md`：`required_before_module_merge` 保持 `false`（已正确）

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
  "requires_network": false,
  "capabilities": ["xlsx", "xlsm", "batch", "incremental", "service_requests"]
}
```

- `requires_network: false`：模块自身不发起网络请求；AI 网络调用由框架统一管理
- `capabilities`：声明模块支持的输入和运行模式

### 2.6 默认运行安全

- `self-check`：生成内存工作簿，不读取凭据，不联网
- 测试：所有测试使用虚构数据，不联网
- CLI draft/finalize：不读取 API Key，不直接调用模型网关

---

## 3. 测试结果

| 检查项 | 命令 | 预期 |
|---|---|---|
| 单元测试 | `python -m pytest modules/after_sales/tests -q` | 全部通过 |
| Ruff | `python -m ruff check modules/after_sales` | 通过 |
| 静态合同 | `python -m app.tools.module_contract_cli validate modules/after_sales` | 通过 |
| 版本 | `modules\after_sales\run_module.bat version` | `after_sales 1.1.1` |
| 自检 | `modules\after_sales\run_module.bat self-check` | 通过 |

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
| draft 阶段生成 service_requests | ✓ |
| AI 拒绝后离线降级 | ✓ |
| 人工复核三项必审字段写回 | ✓ |
| finalize 不重复调用 AI | ✓ |
| finalize 网络调用次数为 0 | ✓ |

---

## 6. 需要框架重点复验的接口

1. **service_requests**：draft 阶段的 `result.json` 中 `service_requests` 字段结构与合同一致性
2. **service_response_file**：finalize 阶段的响应信封解析、身份校验和降级路径
3. **人工复核三项**：售后费用、责任工厂、投诉类型三项阻断确认的正确生成和写回
4. **confirmation_file 写回**：人工确认值在最终 Excel、JSON、图表和报告中的一致性
5. **module.json 合同**：`capabilities` 和 `requires_network` 与行为一致
6. **自检不联网**：默认 `self-check` 和测试不应读取凭据或发起网络请求

---

## 7. 回滚

- PR 合并前：关闭 Draft PR，分支不受影响
- PR 合并后：回滚 PR 合并提交
- 回滚基线：`integration` 最新提交
