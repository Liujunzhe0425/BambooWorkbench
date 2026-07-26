> 文档状态：历史归档
> 不作为当前实现和验收依据。
> 当前有效说明以 README 和三份主指导文档为准。

---
request_id: FCR-moisture-20260724-history-summary-append
module_id: moisture
module_version: 1.1.0
owner: moisture模块负责人
status: proposed
framework_areas:
  - ui
  - workflow
breaking_change: false
required_before_module_merge: false
---

# 框架适配请求：历史汇总追加

## 目标

在水分模块“汇总表生产”中增加“历史汇总表＋新原始数据”入口。模块侧已经完成标准四/五表读取、输入角色校验、SHA-256去重、同批冲突确认、确定性重算及新版四表输出；框架不得解析Excel或重新实现合并规则。

## 最小框架改动

1. 页面允许选择一个历史标准汇总表和一个或多个新原始Excel；
2. 框架生成模块私有配置：
   - `operation=append_summary`
   - 一个 `base_summary`
   - 一个或多个 `new_raw`
   - 每个job输入恰好分配一次；
3. 继续使用现有draft/finalize和confirmation流程；
4. 冲突答案只展示模块给出的候选值，不允许框架自行覆盖历史记录；
5. 结果中心仍展示新版XLSX、Markdown和result，不覆盖原历史表。

## 安全与降级

- 输入由TaskService快照，原文件保持只读；
- 不支持的旧表明确失败，不自动猜测字段；
- 重复内容跳过；同批内容冲突必须人工确认；
- 失败不得修改历史文件或影响普通“创建新汇总表”。

## 验收

- 四表和旧五表均可作为历史基表；
- SHA重复及同批相同记录不重复计算；
- 同批不同值产生稳定confirmation，finalize可重放；
- 发布结果按检测日期排序，历史样本和统计值不变；
- 源码和便携版均经Registry/TaskService/Runner/BAT执行；
- 中央Job/Result Schema和其他模块不变。

## 框架方审核

- 审核结论：待审核
- 实施分支/PR：待填写
