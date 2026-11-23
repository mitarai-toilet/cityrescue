# CITYRESCUE AI · 成员 C 灾害仿真交付

## 运行与接入

解压后在本目录运行以下命令，Python 3.9 或更高版本即可。两个 output.json 是冻结快照，可直接给 B、D、E 使用。

```sh
python hazard.py fixed_flood.input.json flood-local.json
python hazard.py fixed_quake.input.json quake-local.json
python -m unittest -v test_hazard
```

E 可直接调用 `from hazard import simulate`，传入 `simulate(scenario, roads, buildings)`。输入样例中 scenario 遵循 v0.1 的 Scenario，后两项是 A 的 Road、Building 实体数组。资产结构、WGS84 坐标与拓扑由上游校验，C 校验所用 ID 的唯一性和情景引用。输出为按分钟递增的帧数组，包括起点、终点和不足一步的末段。每帧含 time_min、state_version、road_states、building_states。帧包装及 params 子字段为 C 的接入约定，实体字段依据所附契约第三章。团队契约 v0.1 已冻结，正式字段定义见仓库 contracts/schemas。仓库接入入口见 backend/c_hazard.py。

| 输出实体 | 字段及消费规则 |
|---|---|
| RoadState | road_id 关联 Road；time_min 为整分钟；status 取 open/caution/closed；depth_m 为米，地震为 null；risk_penalty_min 为非负分钟；reason 为原因，source 标记 hazard/manual；state_version 为帧序号，从 0 起。 |
| BuildingState | building_id 关联 Building；time_min 与同帧一致；risk_level 取 low/medium/high/unknown；reason 说明分级依据。 |

D 选同一运行、同一帧，按 road_id 连接路网，先删除 closed 的双向或单向边，再对 caution 增加 3 分钟选路成本。ETA 单算行驶时间。closed 的惩罚字段为 0，识别禁行必须读 status。E 负责跨运行 run_id 和交互更新时的全局版本，模块内的版本只在单次输入内有效。

## 洪涝公式与参数

初始积水为零。固定雨强下，道路水深为 h(t) = max(0, I × F − Q) × t / 60000 米，等价于每步按净流入累积。I 是 rainfall_mm_h（毫米/小时，必填），F 是 catchment_factor 按道路 ID 指定的汇水面积倍率（默认 1，0 至 100），Q 是 drain_mm_h（等效排水强度，默认 10 毫米/小时）。t 为累计分钟，60000 同时换算小时与米。水深保留六位小数后判级。h ≥ closure_depth_m 判 closed（默认 0.30 米），否则 h ≥ caution_depth_m 判 caution（默认禁行阈值的三分之一），其余 open。阈值是演示参数。building_road 把建筑关联到相邻道路，以该路水深等级映射 low/medium/high，缺少映射为 unknown。

固定洪涝每 10 分钟输出一次，共 7 帧。SIM-R09 的 I=80、F=5、Q=10，第 40 分钟深 0.26 米，第 50 分钟深 0.325 米，转为禁行。人工封路映射 manual_closed_from_min 指定生效分钟，在首个达到该时间的帧覆盖道路通行状态，保留水深和建筑积水等级。

## 固定地震与适用边界

地震影响区以预先选定的资产 ID 集合表示。road_status 将 SIM-R09、SIM-R14 设为 closed，SIM-R07 设为 caution；其余 open。building_risk 将 SIM-B01 设为 high，未配置建筑为 unknown。状态从第 0 分钟生效并持续至结束。两个灾种共用输出实体。seed 是契约必填整数，当前两种模型均无随机项，改变 seed 也不会改变数值。

样例的四条道路与一栋建筑均为团队契约之外单独构造的合成测试片区，ID 用于演示引用。汇水倍率、排水、阈值和地震分区均未经实测校准。模型省略地形、路段间水流、管网容量变化、震动传播和结构响应。建筑风险表示情景暴露等级；真实校园推演需 A 提供资产并重新配置映射。

## 验收记录

详见 test-record.txt。固定输入的两种输出各重复核对三遍；独立路网消费者实测正常通路、洪涝绕行、人工封路不可达及地震不可达。取得 D 的实现后，用同一输入中的 roads 和第 60 分钟 road_states 调用正式规划入口，检查 N1 至 N4 的路线只有 SIM-R07、SIM-R14；再人工关闭 SIM-R14，预期不可达。完整节点名均带 SIM- 前缀。实际 D/E 仓库联调与团队契约冻结由团队确认。
