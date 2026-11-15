# CITYRESCUE AI 数据契约 v0.1

本目录定义团队共享的 JSON Schema Draft 2020-12 实体契约。实体 Schema 位于 `contracts/schemas/`；较早的 `schema_v0_1.json` 和 `sample_v0_1.json` 为兼容旧消费者保留的聚合格式，不应继续扩展为第二套规范。新模块使用实体 Schema 与 `data/fixtures/synthetic_campus/` 样例。

## 实体与规则

- Campus：校区范围内唯一 `campus_id`；`data_origin` 为 `real`、`estimated`、`synthetic`；`verified` 表明是否核验。样例校区为 synthetic。
- Node：校区内唯一 `node_id`，Point 坐标为 WGS84 `[longitude, latitude]`。
- Road：校区内唯一 `road_id`，引用 `from_node`、`to_node`；`length_m` 为米，`speed_kmh` 为 km/h，`one_way` 决定方向；GeoJSON LineString。
- Building：校区内唯一 `building_id`；Polygon/MultiPolygon；`height_m` 可空，禁止把估算高度称为实测。
- Scenario：`hazard_type` 为 `flood` 或 `earthquake`，参数放在 `params`，持续时间与步长为分钟，`seed` 为整数。
- RoadState：统一表达两类灾害和人工封路；`status` 为 `open/caution/closed`，`depth_m` 为米或 null，`risk_penalty_min` 为分钟；`state_version` 标识快照。
- BuildingState：`risk_level` 为 `low/medium/high/unknown`；不是倒塌概率。
- Vehicle：引用有效 `node_id`，能力标签及 `available_at_min`（分钟）。
- Event：引用有效 `node_id`；`priority=1` 最紧急；需求量为正整数。
- DispatchResult：路线以 `road_ids` 表示；`eta_min` 是行驶到达时间，不能把风险惩罚直接当 ETA；不可达可用空路段并说明原因。
- ExplainResult：以 `run_id`、`state_version` 和 `evidence_ids` 绑定计算记录；解释不得创建或改写业务 ID/调度结果。

## 文件与读取

固定样例文件在 `data/fixtures/synthetic_campus/`：`campus.json`、`nodes.geojson`、`roads.geojson`、`buildings.geojson`、`vehicles.json`、`events.json`、`flood_scenario.json`、`earthquake_scenario.json`、`road_states.json`、`building_states.json`、`manual_closure_snapshots.json`、`expected_routes.json`。所有数据为合成数据，坐标是占位坐标，不代表任何真实校园地图。

GeoJSON Feature 的业务 ID 位于 `properties`。读取 JSON 示例：`json.loads(Path(path).read_text(encoding="utf-8"))`。运行数据检查：`python -m pytest -q tests/test_contracts.py tests/test_fixture_integrity.py`。

## 版本与团队交接

冻结 v0.1 前，公共字段不得由成员自行改名。契约变更先由提出者开 PR，说明兼容性、迁移方案并同时更新 Schema、fixture 和测试；E 组织评审，五人确认后合并。破坏性字段调整应升主版本；兼容增量更新版本/变更记录。

- A 输入来源及许可记录，输出 Campus、Node、Road、Building 与设施空间数据。
- B 读取空间数据、RoadState、DispatchResult，绘制底图、风险层、车辆和路线。
- C 读取 Scenario 与空间资产，输出 RoadState、BuildingState。
- D 读取 Road、RoadState、Vehicle、Event，输出 DispatchResult。
- E 维护 API 编排与 `state_version`，消费真实计算证据生成 ExplainResult。

各成员不得自行重新命名公共字段。样例中的人工封路版本递增仅用于数据测试，不证明后端版本冲突拦截已实现。
