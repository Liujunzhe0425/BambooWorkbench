---
request_id: FCR-moisture-20260726-monthly-rollup-learning
module_id: moisture
module_version: 1.3.0
owner: moisture 模块负责人
status: proposed
framework_areas:
  - contract
  - workflow
  - service
  - storage
  - ui
  - packaging
breaking_change: false
required_before_module_merge: true
---

# 框架适配请求：水分模块月度快照、年度累计与确认学习接入

## 1. 业务目标与使用场景

工作台 v1.3.0 按“模块＋年份＋月份”维护唯一正式月度结果。水分模块在当月
finalize 完成后提供不可变结构化快照；框架把同年截至目标月的正式快照和当前候选
快照按月份升序传给模块，模块完全离线生成一整套累计 Excel、普通报告、图表和
业务记录。

较早月份被替换时，框架重新提供替换后的快照集合，模块无状态重算该月及已有后续
月份成果。任何重算失败都不得切换正式月份或覆盖旧成果。

供应商和部门映射 confirmation 另外提供稳定、脱敏的学习描述。框架只能据此调整
下次确认页的默认建议，最终答案仍由用户人工提交。

## 2. 当前限制

当前 integration 的公开合同不能完整承载该流程：

1. `module.json` 没有 `monthly_rollup` capability 的合同描述结构；
2. JobRequest/ModuleResult 没有正式年月事务或内部月度快照登记约定；
3. Registry/Runner 没有累计请求、响应 Schema 的发现和独立进程调用规则；
4. TaskService 没有月度槽位、候选替换、后续月份重算和一次性提交事务；
5. ConfirmationPrompt 没有可选、版本化 `learning` 描述；
6. 结果页没有“内部快照隐藏、累计业务工件展示”的统一规则；
7. 便携运行时没有累计入口和模块私有 Schema 资源验收。

模块已经完成以下私有资产，但在框架合同批准前不会写入 manifest 或现有 result：

```text
schemas/moisture-monthly-snapshot.schema.json
schemas/moisture-monthly-rollup-request.schema.json
schemas/moisture-monthly-rollup-response.schema.json
schemas/moisture-learning-descriptor.schema.json
```

## 3. 请求的框架改动

### 3.1 必须具备：manifest 与合同发现

请发布统一的 `monthly_rollup` capability 描述。建议模块清单采用：

```json
{
  "capabilities": ["monthly_rollup"],
  "monthly_rollup_contract": {
    "schema_version": "1.0",
    "snapshot_schema": "schemas/moisture-monthly-snapshot.schema.json",
    "request_schema": "schemas/moisture-monthly-rollup-request.schema.json",
    "response_schema": "schemas/moisture-monthly-rollup-response.schema.json"
  }
}
```

最终字段名以框架批准版本为准，但必须满足：

- Schema 路径只能是模块目录内安全相对路径；
- Registry 拒绝绝对路径、`..`、越界、链接和不存在的 Schema；
- 请求启动前、响应读取后均按模块 Schema 校验；
- 老模块未声明该 capability 时继续按原流程运行；
- 正式 capability 发布前，框架不得依据文件存在自行推断支持。

### 3.2 必须具备：finalize 月度快照登记

水分 finalize 成功后将生成：

```text
moisture-monthly-snapshot.json
```

建议继续使用现有 ModuleResult `outputs`，以框架批准的内部类型登记：

```json
{
  "type": "monthly_snapshot",
  "path": "<output_dir 内绝对路径>",
  "label": "水分月度快照（内部）",
  "mime_type": "application/json"
}
```

框架必须：

1. 校验路径包含性、链接/reparse、文件存在和模块 snapshot Schema；
2. 计算并保存 SHA-256；
3. 将该工件标记为内部工件，不在客户成果列表中直接展示或打开；
4. 只有 finalize、累计渲染和全部工件校验成功后才允许正式月份事务提交；
5. snapshot 失败时不得伪造 finalize 或累计成功。

如果框架选择新增 `internal_artifacts` 字段而不是复用 `outputs`，必须先发布中央
Schema 和兼容策略，模块再做映射；模块不会自行扩展中央 result。

### 3.3 必须具备：累计进程入口

建议复用正式任务 BAT，新增独立命令：

```text
run_module.bat rollup --request <absolute-request.json> --response <absolute-response.json>
```

进程规则：

- request/response 为不同的框架授权绝对路径；
- Runner 强制离线，不注入 Provider、API Key 或联网许可；
- stdout 每行只能是合法进度 JSON，普通诊断进入 stderr；
- response 最后使用同目录临时文件、`fsync` 和 `os.replace` 原子发布；
- 成功退出码为 `0`；
- 请求/Schema/路径错误为 `2`；
- 工件或响应原子写失败为 `3`；
- 未转换内部错误为 `4`；
- 错误只返回稳定错误码，不返回 traceback、绝对路径、环境变量或输入内容。

模块私有请求字段已冻结为：

```text
schema_version
module_id
target_period {year, month}
snapshot_root
output_dir
network_allowed = false
business_config {version, sha256}
snapshots [{month, path, sha256}]
```

成功响应字段已冻结为：

```text
schema_version
module_id
status
target_period
used_months
snapshot_hashes
record_count
artifacts [{path, type, label, mime_type, sha256}]
```

模块当前以稳定 `MonthlyRollupError.code` 抛出失败。框架请批准统一失败响应外壳；
适配时模块只做异常到批准外壳的机械映射，不降低校验标准。

### 3.4 必须具备：TaskService 月度事务

TaskService/存储层负责：

1. 按 `(module_id, year, month)` 管理正式月份槽位；
2. 把同年不晚于目标月的正式快照和当前候选按月份升序传入；
3. 允许月份缺口，拒绝跨模块、跨年、重复、乱序和晚于目标月；
4. 创建框架授权的独立 snapshot root 和暂存输出目录；
5. 校验累计响应工件相对路径、SHA-256、MIME 和包含性；
6. 替换较早月份时为该月及已有后续月份准备全部重算；
7. 只有全部重算 validated 后一次提交正式槽位、输出和学习证据；
8. 任一失败保持旧正式月份、旧输出和旧学习权重完全不变；
9. 模块不保存月份槽位、数据库事务或“当前正式月份”状态。

### 3.5 必须具备：Confirmation learning

中央 ConfirmationPrompt 增加可选、版本化 `learning` 对象，其内容由模块提供并按
模块私有 Schema 校验。框架不得根据 `rememberable=true` 自行推断学习场景。

首批水分模块只为以下类型提供：

```text
supplier_mapping
department_mapping
```

学习描述字段：

```text
learning_key
field
context
context_levels
candidates [{candidate_id, display_text}]
base_suggestion
preference_adjustable
```

框架行为：

- 从最精确 context level 开始匹配，有证据时不混入更宽层；
- 只在 `preference_adjustable=true` 且候选仍属于模块集合时调整 UI 默认项；
- 用户仍必须人工提交答案；
- 任务学习开关开启、finalize 成功、累计成功且成为正式月份后证据才生效；
- 替换/移除月份通过可审计失效记录撤销旧证据，不物理修改历史；
- 非学习 confirmation 没有 `learning` 字段，框架不得补造。

### 3.6 页面、结果与便携运行时

- 历史数据页按模块和年份显示十二个月，进入月份时展示截至该月的累计成果；
- 客户结果页展示累计 XLSX、Markdown、图表和业务记录，不展示内部 snapshot；
- 累计失败显示稳定错误和可重试状态，不切换正式月份；
- 源码与便携版必须使用同一 Registry/Runner/TaskService 调用链；
- 便携包必须包含四份模块私有 Schema 和累计入口代码；
- `version`/`self-check` 应验证声明的 Schema 存在且合法；
- 不得直接 import `moisture.application.*` 绕过模块进程。

## 4. 责任边界

### 模块方已经完成

- finalize 最终 `WorkbookBatch` 到单月不可变快照的私有内核；
- 同年有序快照的无状态、完全离线累计渲染；
- 四表 XLSX、普通 Markdown、趋势图和累计业务记录输出；
- 跨年、缺月、乱序、重复、哈希、路径、写入失败和早期替换测试；
- supplier/department mapping 稳定学习键、候选 ID、脱敏 context 和回退层级；
- 模块私有 Snapshot/Rollup/Learning Schema、fixture 和测试。

### 等待框架提供

- manifest 正式描述；
- finalize 内部工件登记规则；
- 累计公共进程 envelope、Runner 和 TaskService；
- 月度槽位、重算事务、学习证据存储与撤销；
- 历史数据/结果 UI；
- 便携包统一调用和验证。

### 仍由模块方负责

- 水分公式、Decimal、统计、规则、阈值、颜色、Excel、图表、报告；
- 快照业务字段、累计恢复和离线渲染正确性；
- learning key/candidate ID 和允许学习类型；
- 适配后模块 BAT/CLI 映射与模块相关测试。

### 仍需业务负责人批准

- `0.55/0.47` 阈值继续是待业务批准筛查值；
- 规则、经验内容和适用范围；
- 允许学习的 confirmation 类型扩展。

## 5. 数据、安全与权限

- 累计进程必须强制离线，模块不读取凭据、不调用 Provider；
- snapshot/response/learning context 不得包含 API Key、Header 或绝对输入路径；
- learning context 不含客户身份、文件名、sheet、source row 或自由文本；
- request 中运行时绝对路径仅用于本次授权进程，不写入响应、成果、日志或数据库展示；
- 所有 snapshot 与 artifact 使用 SHA-256 做完整性校验，不作为身份认证；
- 所有外部路径执行包含性、symlink/junction/reparse 和越界校验；
- 学习只调整 UI 默认建议，不能自动提交确认、修改规则或形成业务结论；
- 框架不得把模块业务记录作为通用知识文本重新解释或改变确定性结果。

## 6. 兼容性与迁移

- 是否破坏现有合同：否，新增 capability 和可选 learning 字段；
- v1.2.0 模块继续运行原 draft/finalize、历史追加和管理合同；
- 未声明 `monthly_rollup` 的旧模块不进入月度累计流程；
- v1.3.0 接入前，模块私有内核和 Schema 不对 GUI 宣称可用；
- 旧任务继续保留普通任务历史，不反向伪造月度 snapshot；
- 升级时若存在非终态 moisture 任务，先完成或取消后再启用月度事务；
- 回滚框架 capability 后，停止创建新月度任务，保留既有结果只读；
- 回滚不得删除历史 snapshot、累计成果或学习失效记录。

## 7. 验收标准

1. Registry 发现正式 moisture，并校验四份模块私有 Schema；
2. finalize 通过真实 Runner/BAT 生成并登记内部月度 snapshot，客户结果页不显示该工件；
3. 1 月、1→2 月、缺 2 月的 1→3 月累计均生成完整 XLSX、Markdown、图表和业务记录；
4. 跨年、重复、乱序、哈希错误、路径越界全部结构化拒绝；
5. 替换 1 月后，1 月及已有后续月份全部使用新集合重算；
6. 任一后续月份重算失败时，正式槽位和所有旧成果保持不变；
7. 累计期间 Provider、AI、Knowledge 和 confirmation 请求数均为 0；
8. supplier/department 学习只改变确认页默认建议，用户仍必须提交；
9. sheet/default year/formula/rule scope/history conflict 不产生学习证据；
10. 源码和便携版走相同进程合同，stdout、退出码、路径和错误脱敏通过；
11. v1.2.0 普通任务、历史追加、经验/规则管理和规则快照回归通过；
12. 模块、相关框架集成测试和仓库门禁通过。

## 8. 备选方案与影响

- 已考虑：框架直接 import 模块 Python 内核；
- 未采用：破坏进程隔离、便携兼容和模块责任边界；
- 已考虑：模块自行保存月份槽位和重算事务；
- 未采用：会与框架任务数据库、正式结果发布和跨模块历史页冲突；
- 已考虑：继续复用普通 JobRequest 暗塞快照路径；
- 未采用：中央 Schema `additionalProperties=false`，且会混淆普通检测与离线累计；
- 影响框架：Registry、合同、Runner、TaskService、存储、历史数据/结果 UI、便携打包；
- 影响其他模块：统一 capability/envelope 可复用于水煮和售后，但业务 Schema 独立；
- 主要风险：正式月份事务部分提交、路径越界、旧证据未撤销和 UI 误把建议当答案。

## 9. 附件与证据

- 批准设计：`docs/superpowers/specs/2026-07-26-bambooworkbench-v1.3.0-design.md`
- 模块实施计划：仓库外 `plan/水分模块v1.3.0月度快照与年度累计-混合开发实施计划.md`
- 模块日志：仓库外 `日志/moisture-v1.3.0-rollup/`
- 脱敏 fixture：
  - `tests/fixtures/monthly/snapshot-example.json`
  - `tests/fixtures/monthly/rollup-response-example.json`
  - `tests/fixtures/learning/learning-descriptor-example.json`
- 当前 PR：原 Draft PR #52，目标保持 `integration`

## 10. 框架方审核（由框架负责人/Codex填写）

- 审核结论：待审核
- 判断理由：
- 实施分支/PR：
- 验证范围：
- 对模块交付的后续要求：
