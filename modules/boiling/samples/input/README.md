# 脱敏输入样例

工作簿已按仓库二进制夹具规则移至 `tests/fixtures/boiling/samples/input/`，均为人工构造的虚拟数据：

1. `01_all_pass.xlsx`：字段完整、观察范围内、剥离合格。
2. `02_density_observation.xlsx`：密度超暂存范围。
3. `03_expansion_observation.xlsx`：家具用途膨胀率超暂存阈值。
4. `04_peel_fail.xlsx`：原表浸渍剥离不合格。
5. `05_retest.xlsx`：含普通试件和复测试件。
6. `06_three_samples.xlsx`：试件数量变化为3个。
7. `07_empty_incomplete.xlsx`：空/未完成表，不进入正常统计。
8. `08_calculation_conflict.xlsx`：原表值与复算值冲突。

样例不包含真实企业、人员、订单、客户路径或原始业务数据。
