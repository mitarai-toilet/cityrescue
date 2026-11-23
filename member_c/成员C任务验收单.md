# 成员 C｜灾害仿真

**成员 C 交付进度：7/7。团队联合验收：待 D 使用正式算法复验。**

- [x] **P0 核对统一数据契约及灾害仿真输入输出接口**　已按所附《统一数据契约规范 v0.1》核对字段。入口 [SimulationProvider.simulate](simulation_provider.py) 接收 Scenario、Road 数组和 Building 数组，按时间片返回道路与建筑状态。正式适配器见 [backend/c_hazard.py](../backend/c_hazard.py)，实现 scenarios 和 replay，并由 RunStore 执行 contracts/schemas 校验。
- [x] **P0 完成简化洪涝积水计算模型**　[洪涝计算模块](hazard.py) 根据雨强、路段汇水倍率、排水强度和历时计算非负积水深度，再按警戒与禁行阈值输出 open、caution 或 closed。
- [x] **P0 生成不少于六个时间片的洪涝道路状态**　[九龙湖洪涝输出](jlh_flood.output.json) 包含 0、10、20、30、40、50、60 分钟共 7 帧，每帧覆盖 7 条演练道路。第 50 分钟 JLH-R2 深 0.325 米，达到 0.30 米禁行阈值。
- [x] **P0 完成至少一组固定地震影响情景**　[地震输入](jlh_earthquake.input.json) 固定道路与建筑影响范围。[地震输出](jlh_earthquake.output.json) 中 JLH-R2 封闭、JLH-R6 谨慎通行，经管楼的情景风险为 high。
- [x] **P0 统一输出 RoadState、BuildingState**　两类灾害共用 road_states 和 building_states 数组。道路记录包含道路 ID、时间、状态、水深、风险惩罚、原因、来源和版本；建筑记录包含建筑 ID、时间、风险等级和原因。地震道路水深为 null。
- [x] **P0 完成固定样例、边界参数及可复现性测试**　[专项测试记录](test-record.txt) 记录 9 项测试全部通过。覆盖双灾种固定快照、重复运行、零降雨、强降雨、阈值相等、非法参数、末段不足一步，以及封路后的绕行与不可达。
- [x] **P1 整理仿真公式、参数含义及模型局限说明**　[模型说明](README.md) 给出公式、参数单位、默认值和判级规则。[校园接入说明](校园接入.md) 标明地标来源、估算建筑轮廓、合成道路和未经实测校准的灾害参数。

## 交付物

| 类别 | 文件 |
|---|---|
| 洪涝与地震仿真模块 | [模型源码](hazard.py)、[成员 C 接入入口](simulation_provider.py) |
| 固定输入与输出样例 | [洪涝输入](jlh_flood.input.json) / [输出](jlh_flood.output.json)；[地震输入](jlh_earthquake.input.json) / [输出](jlh_earthquake.output.json) |
| 专项测试记录 | [执行结果](test-record.txt)、[模型回归用例](test_hazard.py)、[校园样例验收用例](test_jlh.py) |

## 验收标准

| 标准 | 当前结果 |
|---|---|
| 相同输入生成一致的灾害状态 | 已通过。两组基准情景分别运行三次并与冻结快照比较，结果一致；九龙湖两种情景经 Provider 生成的结果也与各自快照一致。 |
| 禁行道路可被 D 的算法正确识别 | C 侧已验证按 status=closed 可剔除禁行路段。D 正式联调待签核：使用九龙湖洪涝第 50 分钟状态，为 JLH-N1 至 JLH-N3 规划路线，预期可达且不含 JLH-R2。 |
