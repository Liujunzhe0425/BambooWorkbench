# 水煮实验分析报告

- 规则版本：`2026.07-draft`
- 纳入正常汇总的文件：7
- 异常/观察项：6
- 待确认项：2

> 客户未确认的阈值仅用于观察和复核，不构成正式合格/不合格结论。

## 文件摘要

| 文件 | 批号 | 产品 | 试件数 | 平均密度 | 平均膨胀率 | 剥离结果 |
|---|---|---|---:|---:|---:|---|
| 01_all_pass.xlsx | DEMO-001 | 脱敏竹集成材 | 2 | 1.200 | 5.00% | 合格 |
| 02_density_observation.xlsx | DEMO-002 | 脱敏竹集成材 | 2 | 1.450 | 5.00% | 合格 |
| 03_expansion_observation.xlsx | DEMO-003 | 脱敏竹集成材 | 2 | 1.200 | 10.00% | 合格 |
| 04_peel_fail.xlsx | DEMO-004 | 脱敏竹集成材 | 2 | 1.200 | 5.00% | 不合格 |
| 05_retest.xlsx | DEMO-005 | 脱敏竹集成材 | 3 | 1.200 | 5.00% | 合格 |
| 06_three_samples.xlsx | DEMO-006 | 脱敏竹集成材 | 3 | 1.180 | 4.00% | 合格 |
| 08_calculation_conflict.xlsx | DEMO-008 | 脱敏竹集成材 | 1 | 1.200 | 5.00% | 合格 |

## 异常与复核

- **warning / average_density_g_cm3**：平均密度超出当前暂存阈值；该规则尚未获客户确认，不能作为正式合格判定。
- **warning / average_expansion_ratio**：平均膨胀率超出当前产品用途对应的暂存阈值；规则尚未获客户确认。
- **warning / immersion_peel_result**：原表记录浸渍剥离检测不合格。
- **critical / samples**：缺少关键字段 samples，该文件未进入正常汇总统计。
- **warning / density_g_cm3**：样1 的原表值与模块复算值不一致。
- **warning / expansion_ratio**：样1 的原表值与模块复算值不一致。

## 人工确认

- `C-CONFLICT-1-603761a3a3d3`：样1 原表值与复算值冲突，需要人工选择可信来源。
- `C-CONFLICT-2-603761a3a3d3`：样1 原表值与复算值冲突，需要人工选择可信来源。
