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

## 灾害状态管理 API

本节是 2026-11-22 的后端接口设计决策，未修改冻结的公共实体 Schema。
本轮已实现固定情景回放和进程内运行隔离，没有实现真实灾害模型。

| 方法与路径 | 请求/响应 |
| --- | --- |
| GET /api/v1/scenarios | 现有洪涝、地震 Scenario 数组 |
| GET /api/v1/scenarios/{scenario_id} | 对应 Scenario 实体；不存在返回 404 |
| POST /api/v1/simulation/runs | 创建回放运行；201 返回运行信息包装 |
| GET /api/v1/simulation/runs/{run_id} | 运行信息、当前版本和来源 |
| GET /api/v1/simulation/runs/{run_id}/roads | 当前运行的 RoadState 数组 |
| GET /api/v1/simulation/runs/{run_id}/buildings | 当前运行的 BuildingState 数组 |
| GET /api/v1/simulation/runs/{run_id}/state | 运行信息加 roads/buildings 的完整快照 |

创建洪涝回放请求：

```json
{"scenario_id":"SIM-FLOOD-01"}
```

创建地震回放请求：

```json
{"scenario_id":"SIM-EARTHQUAKE-01","params":{"affected_road_ids":["SIM-R09","SIM-R14"],"building_risk_seed":42}}
```

`params` 可省略或为 null，表示使用该 Scenario.params；显式提供时必须与固定情景完全相同，
否则返回 422 `unsupported_replay_parameters`。不接受顶层 seed、duration_min、step_min
等覆盖字段，也不接受自定义灾种或任意输入 Scenario；这些字段由查询到的 Scenario 决定。
这是固定数据回放限制，不是对冻结 Schema 新增字段规则，也不代表能计算不同降雨或强度。

运行信息响应结构如下（run_id 的占位字符串说明结构，真实值由服务器生成）：

```text
{
  run_id: "run-<随机 UUID hex>",
  scenario_id: "SIM-FLOOD-01",
  state_version: 0,
  time_min: 20,
  mode: "fixture_replay",
  data_origin: "synthetic",
  scenario: <原始 Scenario 实体>,
  provenance: <说明所用 fixture 文件和处理方式的字符串数组>
}
```

整体 state 响应在上述包装上增加 `roads`、`buildings` 数组，内部严格使用冻结实体。
OpenAPI 直接嵌入对应实体 Schema，并定义运行包装的必填字段与类型；包装字段不属于实体契约。

### 实际 fixture 支持边界

- 洪涝：读取 road_states.json 的第 20 分钟快照，SIM-R09 关闭；没有洪涝建筑 fixture，
  因此 buildings 返回空数组，表示无可用输出，不表示建筑没有风险。
- 地震：现有 fixture 没有完整地震道路快照；provider 仅取 road_states.json 第 0 分钟的道路 ID，
  使用 earthquake_scenario.json 的 affected_road_ids 固定关闭 SIM-R09、SIM-R14。
  所有道路输出时间为 20，非关闭道路为 open，depth_m=null、risk_penalty_min=0；这是
  明示的回放适配规则，未计算地震危险度，也未复用洪涝水深/风险。
  建筑状态读取 building_states.json，5 栋建筑 risk_level 均为 unknown。
- provider 校验状态 Schema、道路/建筑引用、重复道路时间片、时间步长及当前快照道路完整性。
  地震建筑状态时间必须与快照一致；数据错误不发布部分运行。
- 此处只初始化一个固定快照，不实现自动时间推进、全时间线播放或真实计算。

### 运行编号和版本

`scenario_id` 指可复用的固定情景；每次 POST 都产生独立的 `run_id`，包括重复的 scenario_id。
每个运行初始 `state_version=0`，把回放道路实体内的版本统一为当前运行版本，
不把 fixture 的历史版本当作运行版本。原 fixture 文件不变。BuildingState 没有版本字段，
它与 roads 同属外层快照版本。

创建新运行不替换任何已有运行、不修改校园空间数据；无全局“当前运行”。
GET 返回防御性副本，不改变版本。版本编号仅在 run_id 内比较，不能跨运行比较。
未来人工封路入口应对完整校验后的新快照作原子发布，每次成功修改加 1，
但本轮未实现更新 API、旧版本冲突拦截或派车。

每个 FastAPI app 实例有一个 RunStore；锁保护原子发布和读取，防御性拷贝隔离调用方。
所有 provider 输出通过验证后才进入发布点。尚无容量限制/淘汰策略，适用于短期单进程联调。
进程重启、reload 或新 app 实例会丢失全部 run_id；请使用单 worker，多个 worker 的内存不共享。
创建新 app 后查询旧运行返回 404。线程锁不提供跨进程一致性。

### 错误与 provider 对接

不存在的情景/运行返回 404 `scenario_not_found` / `run_not_found`。
非法请求字段或不支持的参数覆盖返回 422；fixture 缺失/JSON 损坏/状态无效返回 503，
包括 `data_file_missing`、`invalid_json`、`invalid_simulation_data`、`invalid_reference`。
错误响应沿用 detail.code/message 包装；404 code 无 message 也是有效响应。

C 可实现 `backend.simulation.SimulationProvider`，提供：

```python
def scenarios(self) -> list[dict]: ...
def replay(self, scenario: dict) -> Replay: ...
```

返回值为 `Replay(scenario, time_min, roads, buildings, provenance)`；实体必须符合冻结
Scenario/RoadState/BuildingState，引用有效资产，无重复/矛盾状态，时间片一致。
通过 `create_app(simulation_provider=provider)` 注入，不需要更改只读校园 API。
run_id 和运行版本由 E 的 RunStore 维护，C 不分配运行版本。
目前这个接口只定义同步单快照返回；未来真实计算需共同升级 API 模式及来源包装，
当前 `mode=fixture_replay/data_origin=synthetic` 不得直接复用于真实模型的标签。

### 灾害状态测试

```powershell
.\.venv\Scripts\python.exe -m py_compile backend/app.py backend/simulation.py tests/test_campus_api.py tests/test_simulation_api.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_simulation_api.py tests/test_campus_api.py tests/test_contracts.py tests/test_fixture_integrity.py tests/test_schema_validation.py tests/test_api.py
```

测试包含真实 Uvicorn HTTP 请求、Scenario 查询、两灾种创建、Schema 校验、404/422/503、
重复 GET 不变、并发独立创建、深拷贝隔离与重启后运行丢失，以及原校园/健康/契约回归。
需允许本地 HTTP 与线程访问；此前受限执行环境的超时不等同于接口逻辑失败。

本轮最终执行结果（2026-11-22）：**41 passed in 16.70s**，0 failed、0 skipped。
包含 9 项灾害状态测试、7 项校园 HTTP 测试、24 项契约/fixture/Schema 测试和
1 项原 ASGI 健康测试。Python 编译检查通过，冻结 Schema 和空间 fixture 未改动。
