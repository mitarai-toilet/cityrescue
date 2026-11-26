# C/D Provider 接入与后端集成

## 数据流与契约

唯一实体规范为 `contracts/schemas/*.schema.json`，本轮未修改。数据流为：
校园空间文件 → Scenario → SimulationProvider → RunStore 独立快照 → 人工覆盖层 →
IntegrationService → DispatchProvider → 输出校验与版本复核 → 调度历史/响应。
Replay、run 包装及 provenance 是后端内部上下文，不是新增公共实体字段。

## C 接口与接入

实现 `backend.simulation.SimulationProvider` 的同步方法：

```python
from backend.simulation import Replay
from backend.providers import ProviderError

class CProvider:
    def scenarios(self) -> list[dict]:
        raise ProviderError('not_delivered', 503)

    def replay(self, scenario: dict) -> Replay:
        raise ProviderError('not_delivered', 503)
```

Scenario 必须符合 `scenario.schema.json`、campus_id 有效、scenario_id 唯一。
replay 方法名为兼容既有签名保留，接收隔离 Scenario 副本，返回：
`Replay(scenario, time_min, roads, buildings, provenance, mode, data_origin)`。

- roads 是完整 RoadState 数组，覆盖所有道路、ID 唯一、时间片一致。
- buildings 是 BuildingState 数组，引用有效建筑且无重复；空数组表示无可用输出，
  须说明缺失边界，不能解释为建筑安全。
- time_min 为非负整数，符合 step_min，不超 duration_min；返回 Scenario 与所选输入相同。
- provenance 是字符串数组，记录来源与模型局限，不放敏感路径/密钥。
- mode 为 fixture_replay 或 simulation；data_origin 为 synthetic/estimated/real。
  两者分别表示执行模式与数据来源，不能把 fixture 输出标为真实计算。
- run_id 和 state_version 由 E 管理；C 不修改运行存储、路由或 FastAPI Request。

用 `create_app(simulation_provider=CProvider())` 注入。POST 请求仍按 scenario_id
选定 Scenario；params 只接受与对应 Scenario.params 相同的值，不支持任意参数计算或异步长任务。
固定 Provider 复用现有 fixture 读取：洪涝道路第 20 分钟、无建筑输出；地震显式封路及固定建筑状态。
后端统一执行 Schema、空间引用、完整道路集合、时间片和模式校验后才发布新运行。

## D 接口与接入

实现 `backend.dispatching.DispatchProvider`，同步签名：

```python
class DProvider:
    name = 'd_dispatch_v1'

    def dispatch(self, snapshot: dict, spatial: dict,
                 vehicles: list[dict], events: list[dict]) -> dict:
        raise NotImplementedError
```

用 `create_app(dispatch_provider=DProvider())` 注入，也可同时注入 CProvider。
snapshot 包含 run_id/state_version、Scenario、RoadState/BuildingState、time_min 和来源。
spatial 包含 Campus、Node、Road、Building；车辆/任务分别符合 vehicle/event.schema.json。
返回值是 `dispatch_result.schema.json` 定义的 DispatchResult，不返回 HTTP Response。
示例请求、固定 Vehicle/Event 和返回包装见 [后端接口说明](BACKEND_API.md)。

返回标识/版本必须与输入一致；路线只能引用有效、连续、方向正确且非 closed 的道路。
车辆与任务不重复分配，任务由 assignments/unassigned_events 完整覆盖；
不可达 assignment 需空路线和 reason。eta_min 是行驶/到达分钟，不等于 risk_penalty_min；
旧 risk_cost 未定义单位，不可自动换算。后端验证合法性，不负责计算最短路或最优派车。

统一编排入口是 `IntegrationService.dispatch(run_id, version, vehicles, events)`：
受控取快照 → 加载空间数据 → 校验输入 → 用隔离副本调用 Provider → 校验输出 →
重新核对运行版本 → 原子记录结果。Provider 不接收 Request，不得通过闭包访问运行状态。
后端对副本修改和失败结果提供隔离，无法回滚 Provider 自己产生的外部副作用。

默认 FixtureDispatchProvider 严格匹配合成洪涝及单车单任务的两个案例，其他输入 501。
案例位于 `backend/fixtures/dispatch_cases.json`；未实现 D 的算法或真实动态重规划。

## 异常和失败隔离

新适配器可抛框架无关 `ProviderError(code, status)`，status 允许 400、501、503。
公开响应使用受控错误码，不直接公开 Provider 的 code/原异常消息或内部堆栈：

| HTTP | 处理 |
| --- | --- |
| 400 | provider_invalid_parameters |
| 404 | 原有 run_not_found/road_not_found/scenario_not_found |
| 409 | state_version_conflict，含 current_state_version |
| 422 | 保留 FastAPI 请求校验及实体/引用输入错误 |
| 501 | provider_not_supported；旧 fixture 保留 dispatch_input_not_supported |
| 502 | 保留 invalid_dispatch_provider_result |
| 503 | provider_unavailable、invalid_simulation_data 或原来源错误码 |
| 500 | Provider 意外异常 provider_internal_error；其他意外错误 internal_error |

OSError/TimeoutError 作为暂不可用映射为 503；未知 Provider 异常记录于服务端，响应不泄漏细节。
`backend/providers.py` 是统一调用边界；原 fixture HTTPException 行为按已发布兼容规则保留。
异常或非法输出不发布半成品运行，不添加失败调度历史，不改变已有快照。

## 版本和生命周期

每个 run_id 独立，初始版本 0；GET 不递增；有效人工覆盖变化才递增。
open 只撤销人工层，不消除灾害 closed。版本比较/更新在同一锁内；过期修改不改变状态。
调度计算在锁外，保存前再检查版本；计算期间变更则返回 409，不记录过期结果。
内存状态仅适用于单 app/单 worker，重启/reload 丢失运行和历史，不提供持久化或跨进程一致性。

## 运行、测试与真实 HTTP 演示

仓库根目录终端一前台启动服务，结束时 Ctrl+C：

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

终端二：

```powershell
pwsh -NoProfile -File scripts/demo_backend.ps1 -BaseUrl http://127.0.0.1:8000
# 无 pwsh 时使用 powershell -NoProfile -ExecutionPolicy Bypass -File scripts/demo_backend.ps1
.\.venv\Scripts\python.exe -m pytest -q tests
git diff --check
```

脚本只访问 loopback，绕过系统 HTTP 代理，使用现有文件与接口返回的 ID。
需要默认合成数据和固定案例，不启动服务，只创建独立内存运行，不修改旧运行或文件。
检查健康、校园、情景、运行、状态、封路、版本递增、旧请求 409、当前版本固定调度。
输出 PASS/UNCOVERED，失败返回非零。pytest 会限时启动真实 Uvicorn、执行该脚本并清理服务。
本轮曾因 PowerShell 本地请求被代理返回 502，显式绕过代理后脚本通过；Python HTTP 已绕过代理。

## 五人联调最低交付

- A：来源/许可、有效 ID/几何、真实数据覆盖边界。
- B：消费状态和来源包装，携带版本修改道路，显示 409/501/503 与路线失败态。
- C：可导入适配器、依赖、Scenario 参数说明、固定输入输出、时间片和模型局限。
- D：可导入适配器、正常/封路/不可达/无车用例、确定性策略、ETA/风险定义。
- E：配置 Provider、保留输入输出和并发校验，组织两车三任务的真实集成验收。

中期完整救援演示仍需前端展示、C 的真实状态输出、D 的真实路线/调度和跨模块联调。
当前通过证明接口与固定案例调用链，不代表真实灾害、真实路径算法或全系统验收。

## 本轮执行记录

2026-11-22：完整 `python -m pytest -q tests` 结果为 **70 passed, 1 warning in 23.34s**，
0 failed、0 skipped；在原 55 项上新增 15 项集成检查。包括标准 Schema、校园/状态/封路/
并发/调度回归、原 ASGI 健康测试和真实 Uvicorn HTTP 请求。
PowerShell 演示单独执行输出 PASS 和 UNCOVERED，退出码 0，随后完整回归再次通过。
Python 编译、`git diff --check` 通过，冻结契约和空间数据未改。
1 条警告是 Starlette 对 TestClient/httpx 的弃用提示，未升级依赖。
