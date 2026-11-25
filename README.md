# cityrescue

CITYRESCUE AI 是一个面向单一、经核验校园区域的应急决策原型，首期聚焦洪涝与地震情景、救援车辆任务分配、封路后重规划，以及可追溯的决策解释。默认后端使用合成样例。二维工作台另外提供基于 OpenStreetMap 的九龙湖校区演练，车辆、灾情和通行参数为模拟，校区道路通行条件仍待现场核验。

## 技术架构

- 前端：React + TypeScript + Vite + MapLibre（2D 优先；2.5D 可选，具体实现待核实）
- 服务端：Python + FastAPI
- 路网/调度：NetworkX（后续模块）
- 契约：JSON Schema v0.1 与固定模拟样例

## 模块与五人职责

| 目录/角色 | 职责 |
|---|---|
| `frontend/` · B | React 地图和交互；消费统一契约 |
| `data/` · A | 校园空间数据、来源/许可与核验记录；真实数据待提供 |
| `simulation/` · C | 洪涝/地震情景适配器与道路状态 |
| `dispatch/` · D | NetworkX 路网、车辆任务分配及封路重规划 |
| `backend/` · E（队长） | FastAPI、AI/规则解释和系统集成 |
| `contracts/` | 跨模块数据契约和样例 |
| `tests/`、`docs/` | 自动化检查、协作和运行说明 |

## 本地运行

需要 Python 3.11+。在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --reload
```

服务默认地址为 `http://127.0.0.1:8000`，健康检查为 `GET /health`。另开终端运行：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

如使用其他环境，可将 `.venv\Scripts\python.exe` 替换为对应 Python 命令。二维地图与调度工作台的启动和联调步骤见 [前端说明](frontend/README.md)。

## 契约

校园只读查询、响应格式、错误码和测试说明见 [后端 API](docs/BACKEND_API.md)。

v0.1 唯一正式实体契约位于 `contracts/schemas/`，使用 JSON Schema Draft 2020-12；旧聚合文件 `contracts/schema_v0_1.json` 与 `contracts/sample_v0_1.json` 仅作历史兼容参考。合成校园 fixtures 位于 `data/fixtures/synthetic_campus/`，不能作为真实校园资料使用。
