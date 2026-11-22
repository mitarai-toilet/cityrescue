# 校园只读 API

## 开发基线

v0.1 已冻结。唯一正式实体规范是 `contracts/schemas/`，聚合入口引用这些实体，
不另定义字段。道路使用 `from_node` / `to_node`；RoadState 用 `road_id` 引用道路，
BuildingState 用 `building_id` 引用建筑。Scenario 的 `params` 当前只有 object 类型约束，
具体灾种参数需要 C/E 后续共同约定。Vehicle、Event 是调度输入，DispatchResult 是输出。
`risk_penalty_min` 为风险惩罚分钟，独立于行驶 ETA；旧 `risk_cost` 不得直接换算。
RoadState 的 `state_version` 目前为可选非负整数，DispatchResult/ExplainResult 中为必填；
后端运行版本维护与旧版本拦截尚未实现，本轮只读接口不会生成或推进状态版本。

## 启动

仓库根目录执行（Python 3.11+）：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --reload
```

默认地址 `http://127.0.0.1:8000`；交互文档 `/docs`，机器规范 `/openapi.json`。
所有新增接口的 OpenAPI 成功响应直接使用冻结的 JSON Schema；服务器返回前执行标准
Schema 校验与引用检查，不再维护另一套字段模型。

## 接口

| 方法与路径 | 响应 |
| --- | --- |
| GET /health | status、service、version，服务存活检查 |
| GET /api/v1/campus | Campus 实体 |
| GET /api/v1/campus/nodes | Node 实体数组：node_id 与 position |
| GET /api/v1/campus/roads | Road 实体数组，geometry 为 LineString |
| GET /api/v1/campus/buildings | Building 实体数组，geometry 为 Polygon/MultiPolygon |
| GET /api/v1/campus/graph | API 包装对象，含 campus、nodes、roads；内部均为原实体 |

节点响应示例（数组第一个元素）：

```json
{"node_id":"SIM-N1","position":{"type":"Point","coordinates":[121.0,31.0]}}
```

Campus 来源标记为 `data_origin: synthetic`、`verified: false`。完整示例可查询接口，
或读取 `contracts/sample_v0_1.json` 的对应字段。graph 是查询包装，不是新增业务实体。

## 数据来源与错误

默认来源是 `data/fixtures/synthetic_campus/` 的 campus.json、nodes.geojson、
roads.geojson、buildings.geojson。这些是合成占位数据，不代表任何真实校园测绘。
文件路径相对后端模块定位，启动工作目录不影响加载。未改动 A 的空间文件。

空间文件中的 Feature.properties 转为实体属性；节点几何转为 position，
道路/建筑保留 geometry。所有五个查询接口先验证整个空间数据集，
因此任一空间文件异常会令查询返回 HTTP 503。每次请求重新读取，不缓存坏数据，
也不回退到伪造的成功响应。此加载策略适用于当前小规模样例。

错误体示例：

```json
{"detail":{"code":"invalid_reference","message":"Road SIM-R01 references missing Node"}}
```

错误码：`data_file_missing`、`invalid_json`、`data_read_error`、`invalid_geojson`、
`invalid_entity`、`duplicate_id`、`invalid_reference`；实体 Schema 缺失/错误也会明确报错。
几何端点必须对应道路起终节点。建筑几何细节检查仍受冻结 Schema 的既有限制约束。
`/health` 表示服务存活，数据损坏时仍可返回 200，不代表数据集有效。

## 测试与本次结果

```powershell
.\.venv\Scripts\python.exe -m py_compile backend/app.py backend/campus.py tests/test_campus_api.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_campus_api.py tests/test_contracts.py tests/test_fixture_integrity.py tests/test_schema_validation.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_api.py
```

2026-11-22 实测：本轮 API 与原数据回归 **31 passed in 8.41s**；原 ASGI 测试
单独 **1 passed in 0.30s**。API 测试启动真实 Uvicorn，使用空闲本地端口，
请求超时 3 秒、启动限时 10 秒，并在结束后清理进程。
覆盖五个查询响应、OpenAPI Schema、来源标记、数据一致性、健康接口及六类错误。

受限执行环境中同组 HTTP 测试曾出现启动可达性超时（7 failed，24 passed）；
解除执行环境本地网络限制后，代码未变即通过。ASGI 测试也在该环境通过，
没有修改原健康处理函数或测试。尚不能断言所有受限环境的 ASGI 行为已解决。

## 后续集成

已实现：只读空间文件加载、规范校验、引用与重复 ID 检查、校园/路网查询。
尚未实现：真实校园授权数据接入、灾害计算、车辆派遣、重规划、运行版本存储、AI 调用。

下一轮建议 C/E 先约定 flood/earthquake 参数的服务层校验，沿用冻结 Scenario 输入；
由 C 输出 RoadState/BuildingState，E 在运行包装层绑定 run_id/state_version，
先验证对象引用和同快照唯一道路状态，再交给 D。任何实体字段调整须按冻结 PR 流程审批。
