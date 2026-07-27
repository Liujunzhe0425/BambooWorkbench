# 水煮模块 v1.3.0 人工验收后整改与重新交付说明

基线：`integration@b89d5f4d6ebcff73f386ed791a7a0cb017bf35ab`。旧 PR #63 已合并，本轮必须创建新的 Draft PR。

## 当前问题

人工验收任务在 draft 阶段出现 8 个确认项，8 个答案全部匹配；finalize 业务处理成功并生成 4 项用户成果，却返回：

```text
status=success
monthly_snapshot=null
```

中央框架随后拒绝该矛盾结果，任务未发布。

## 问题位置和产生原因

- finalize 重新计算时出现一个 draft 阶段不存在的新确认候选；
- 模块把它转为 `BOILING-FINALIZE-NONBLOCKING-001` 观察项，同时增加 `unresolved_confirmation_count`；
- 结果状态仍被判定为 success，但快照生成条件要求该计数等于零；
- 因此形成“成功但无快照”，现有测试未覆盖 finalize-only 确认集合漂移。

## 责任边界

水煮负责人负责确认集合的确定性、答案应用、成功状态与快照的一致性，以及水煮快照 payload。框架只负责根据最终状态校验和登记，不修改水煮公式、阈值、判定或 Excel。

## 整改需求

1. 相同输入、规则、配置和服务响应下，draft 与 finalize 的确认集合必须确定且可重建。
2. 所有可能影响正式结果的确认应在 draft 暴露；不得在 finalize 静默新增确认后仍报告 success。
3. 明确区分阻断确认与非阻断观察：非阻断观察不得错误阻止合法快照；真正未解决的阻断确认不得生成正式快照。
4. 建立模块内部不变量：带年月的 `success` finalize 必须返回合法顶层 `monthly_snapshot`；无法生成快照必须返回准确的非成功状态和稳定错误。
5. 增加确认集合漂移回归测试，覆盖原表结论与复算规则冲突在 draft/finalize 两阶段的一致性。
6. 增加完整 BAT/CLI 与便携链路测试，确认内部快照不进入普通 outputs。
7. 将水煮模块版本和模块 CHANGELOG 更新为 `1.3.1`，不得修改中央应用版本。

## 必须达到的目标

- 8 个 draft 确认全部提交后，finalize 不新增第 9 个未回答确认；
- 正常业务成功时生成 2026 年 4 月内部快照并进入离线累计；
- 真正存在新阻断条件时不得伪装 success，也不得登记正式月份；
- 不改变水煮业务公式、阈值、等级和客户统计口径。

## 验收标准

- 完整模块测试、Ruff、version/self-check、合同 CLI、`git diff --check` 通过；
- 新增 draft/finalize 确认 ID 集合稳定测试；
- 新增 `success => monthly_snapshot` 合同测试和非成功无快照测试；
- Registry → TaskService → Runner → BAT → snapshot → rollup 在源码和便携环境通过；
- 快照年月、路径、哈希和离线累计结果可由框架复验；
- 不提交真实人工验收 Excel 或绝对客户路径。

## 修改范围限制

仅修改 `modules/boiling/`。不得修改框架、其他模块、integration 或 main。

## 自测要求

至少提供：完整模块测试统计、确认集合稳定测试、成功/失败快照不变量、中央合同 CLI、BAT version/self-check、便携测试、Ruff 和 diff-check。

## 重新交付步骤

1. 同步最新 integration；
2. 在 `module/boiling` 内整改；
3. 创建新的 Draft PR，目标必须为 integration；
4. 框架修复进入 integration 后再次同步并重跑正式链路；
5. 提供 PR 链接、最新 SHA、模块版本 `1.3.1`、修改内容、完整测试结果和重点复验接口。

## 禁止事项

不得更新旧的已合并 PR #63 作为交付，不得指向 main，不得删除快照要求，不得用伪造快照或忽略真实阻断确认使任务通过。

## 给负责人的通知

水煮人工验收失败已定位：draft 的 8 个答案全部匹配，但 finalize 新产生一个确认候选；模块一边把它标记为非阻断观察，一边增加未解决计数，最终返回 success 却不生成 monthly_snapshot。请同步最新 integration，仅在 `modules/boiling/` 内修复确认集合确定性和 success→snapshot 不变量，补充确认漂移、失败状态、BAT 与便携全链路测试。模块版本更新为 `1.3.1`。旧 PR #63 已合并，请创建新的 `module/boiling → integration` Draft PR，并提供 PR、SHA、版本和完整结果。

## 给 AI Agent 的执行提示词

严格只修改 `modules/boiling/`。同步最新 integration，读取 `docs/acceptance/rectification/boiling-post-v1.3.0-2026-07-27.md` 和中央月度合同。复现 draft 8 个确认全部回答后，finalize 又产生一个新确认、unresolved_confirmation_count 非零但 status 仍为 success 的矛盾。保证确认集合确定可重建，区分阻断确认与非阻断观察，并建立带年月 success 必须返回合法顶层 monthly_snapshot 的不变量；非成功不得登记正式月份。补充确认 ID 集合、原表/复算冲突、BAT、离线 rollup 和便携测试。将模块版本与 CHANGELOG 更新为 `1.3.1`，不得修改中央版本、业务公式、阈值、框架或其他模块，不得提交真实客户数据。创建新的 Draft PR 指向 integration，并报告 PR、SHA、版本及全部验证结果。
