# D 岗调度模块交付

实现位于 `backend/networkx_dispatch.py`，公开 `NetworkXDispatchProvider.dispatch(snapshot, spatial, vehicles, events)`，可直接注入 E 的 `create_app`。返回冻结的 `DispatchResult`，使用分钟、`event_id`、`road_ids` 和输入的运行版本。

## 启动与接入

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.dispatch_app:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m pytest -q tests
git diff --check
```

启动后使用现有 `POST /api/v1/simulation/runs`、`POST /api/v1/dispatch` 和道路 close/open 接口，见 [API](BACKEND_API.md)。完整 vehicles/events 使用 `data/fixtures/synthetic_campus/vehicles.json` 和 `events.json`。关闭道路后以响应中的新版本重新调度。过期请求由 IntegrationService 拒绝，计算过程中版本发生变化时也会拒绝保存。

```python
from backend.app import create_app
from backend.networkx_dispatch import NetworkXDispatchProvider

app = create_app(dispatch_provider=NetworkXDispatchProvider())
```

## 算法与约定

- 使用 NetworkX MultiDiGraph。双向道路加两个方向的边，单行道路只保留声明方向。平行道路保留独立 road_id，关闭道路从图中移除。
- 每路段行驶分钟为 `length_m / speed_kmh * 0.06`，选路代价为行驶分钟加 `risk_penalty_min`。open 和 caution 都使用给定惩罚。ETA 只累加选中道路的行驶分钟。
- 任务先按 priority 升序，再按 event_id 字符串排序。只处理 pending，其他状态列入 unassigned_events，供调用方维持覆盖关系。车辆在 available_at_min 不晚于快照 time_min 时进入候选。
- 每个任务选择综合代价最低的可达候选车，平局按 vehicle_id。道路按 road_id 排序建图，同输入和顺序打乱的实体得到可复现结果。任务分配后车辆退出本轮候选。无车或不可达任务进入 unassigned_events，继续处理后续任务。
- Event v0.1 无能力需求字段。需要匹配时，E 可在构造 Provider 时传入 `required_capabilities={'事件ID': ['medical']}`。默认不额外限制，文档中的需求量 demand 保留为业务工作量，当前每事件单车。车辆容量、服务时长和跨轮预约尚需团队明确业务语义。
- 输入保持隔离，Provider 无外部写入。E 管理运行版本、历史与占用状态。相同快照重试得到相同建议，后续轮次需要调用方传入更新的 available_at_min 和事件状态。

## 验证与交付边界

`tests/test_networkx_dispatch.py` 覆盖正常、封路绕行、完全不可达、无可用车、两车三任务、能力映射、单行、平行边、同节点、风险与 ETA 分离、非法引用与快照、双灾种 API 和计算期间封路冲突。实体和固定空间数据沿用仓库文件。

当前数据为 9 节点、16 道路的合成校园。洪涝与地震由 C 的现有 fixture Provider 提供状态，D 运行实际路径算法。现场真实校园核验、C 的灾害模型计算和 B 的展示录屏待各模块联调。出发后的车辆需提供已确认的节点位置，路段内部位置与剩余路段行驶约束需后续接入。

本分支基于 `feature/E-api` 的 Provider 集成接口。建议队长先合并 E 接口，再合并 D 分支。



## 本次执行记录

2026-11-23，Python 3.12，仓库 requirements.txt 安装的依赖，NetworkX 3.7。完整 pytest tests 为 82 passed, 1 warning in 69.38s。警告来自既有 TestClient/httpx 弃用提示。
