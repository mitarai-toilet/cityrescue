# CITYRESCUE AI 中期回归验收报告

测试日期为 2026-11-26（Asia/Shanghai）。被测分支为 `feature/E-api`，提交为
`480c99ce6ef5e73fb7647cf9f87b345c64270868`，与抓取后的 `origin/feature/E-api` 一致。
该提交包含 E 的 `d2a90d5` 与远程 `main` 的 `6498072`，是本轮被测的合并基线。
本报告为验收后新增的未提交文档，被测运行代码与提交一致。

## 环境与命令

Windows，项目 `.venv`。Python 3.11.9、FastAPI 0.163.1、Uvicorn 0.54.0、
pytest 8.4.2、jsonschema 4.26.0、NetworkX 3.6.1、httpx 0.28.1、
Pydantic 2.14.3、Starlette 1.10.0、AnyIO 4.16.0。
原环境的 pytest 9.2.0 超出 `requirements.txt` 的范围，本轮仅在虚拟环境安装符合声明的
8.4.2。安装后 `pip check` 输出 `No broken requirements found.`

```powershell
git status
git fetch origin
.\.venv\Scripts\python.exe -m pip install 'pytest>=8,<9'
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q -f backend tests
.\.venv\Scripts\python.exe -m pytest -v -ra
git diff --check
```

额外 HTTP 验收通过 Python 的仓库测试辅助函数 `test_campus_api.server(DEFAULT_DATA)`
启动新 Uvicorn 子进程，使用测试分配的本机端口及合并基线中的 `backend.app.create_app`。
脚本使用 PowerShell 的 `-NoProfile -ExecutionPolicy Bypass -File` 参数，在同一服务上连续执行两次，
每次向脚本的 `-BaseUrl` 传入该服务地址。退出上下文时由辅助函数清理该子进程。
用于手工复现的文档命令如下，第二条在另一个终端执行两次，结束后在服务终端按 Ctrl+C。

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
pwsh -NoProfile -File scripts/demo_backend.ps1 -BaseUrl http://127.0.0.1:8000
```

## 全量结果

**70 passed / 0 failed / 0 skipped / 1 warning，27.16 秒**。收集 70 项，与此前数量一致。
原 ASGI 健康测试与真实 Uvicorn HTTP 测试均通过。编译检查覆盖 `backend/` 与 `tests/` 的全部
15 个 Python 文件，退出码 0。唯一警告为既有 Starlette TestClient/httpx 弃用提示。

| 范围 | 结果 | 验证内容 |
| --- | --- | --- |
| v0.1 Schema 与 fixture | 通过 | 11 类实体的 Draft 2020-12 检查、聚合离线引用、有效实例与负例、合成数据 ID、路网引用及连通性 |
| 校园 API | 通过 | 健康与校园查询、节点/道路/建筑/图响应、道路几何端点一致性、坏文件的明确错误 |
| 灾害运行 | 通过 | 情景列表和详情、洪涝/地震固定回放、运行唯一性、道路和建筑状态、版本不变、运行隔离 |
| 人工封路 | 通过 | 封闭和恢复、有效操作递增版本、重复操作不递增、历史记录、旧版本拒绝、灾害禁行优先、运行隔离 |
| 调度 API | 通过 | Vehicle/Event 与引用、DispatchResult、路径方向和封路约束、运行和版本绑定、并发失效、固定案例与不支持输入 |
| Provider 和 IntegrationService | 通过 | 注入、拷贝隔离、Schema 和引用校验、失败后状态和历史完整 |
| 错误边界 | 通过 | 400、404、409、422、501、503、500 及既有 502。模拟内部异常中的敏感路径和字符串未返回给客户端 |

## 独立 HTTP 与连续演示

`/health` 和 `/api/v1/campus` 返回 200，校园标记为 `synthetic`。
`/api/v1/campus/{nodes,roads,buildings,graph}` 均返回 200。
两轮脚本均验证健康、校园、情景查询、运行创建 201、状态查询 200、封路 200、旧版本请求 409，
以及受支持的当前版本调度 200。随后从实际运行历史读取调度版本与路段。

| 次数 | 退出码 | 新建 run_id | 封路前后版本 | 调度 |
| --- | --- | --- | --- | --- |
| 1 | 0 | `run-e6d69f7a51d844fc8b04afe822689635` | 0 → 1，旧请求 409 | 版本 0 和 1 均有固定结果 |
| 2 | 0 | `run-ca42c68ce792417595662637ca7bbb60` | 0 → 1，旧请求 409 | 版本 0 和 1 均有固定结果 |

两次均关闭 `SIM-R01`，固定路线从 `SIM-R01, SIM-R02` 变为
`SIM-R07, SIM-R03, SIM-R15`，为预先设定的案例。额外发送合法但不受案例支持的输入，
调度返回 501 `dispatch_input_not_supported`。最后回读两条运行快照和历史，均与各自的
演示结束状态一致，合成校园与调度案例文件的 SHA-256 在演示前后完全一致。

## 合并与交付边界

- A 的 [来源与许可](DATA_SOURCE_AND_LICENSE.md) 和 [路网拓扑核验](ROAD_NETWORK_VALIDATION.md)
  与远程 `main` 上的交付一致。E 的 [Provider 接入指南](INTEGRATION_GUIDE.md)、后端代码、
  测试和演示脚本与 E 基线一致。上一轮合并已解决同名指南冲突，保留 E 的完整正文。
- 冻结点以来 `contracts/` 和合成 `data/fixtures/` 无差异。远程其他成员分支已抓取，
  它们的未合并代码未纳入本次测试。文档启动和演示参数已与实际入口核对。
- 合并结果未发现功能回归，本轮无代码修复。工作区仅新增此报告并保留原有未跟踪 Word 文件。
  `git diff --check` 通过，未见未解决冲突、Schema 或数据改动，无暂存文件。
- 真实四牌楼数据包未接入本基线，A 的文档记录的是其独立拓扑工作，真实路网加载、许可落地和
  现场道路通行情况未验收。C 的实际灾害计算、D 的真实调度与动态重规划、B 的前端和五人
  端到端联调均未验收。

**结论：中期代码内部验收通过，建议冻结此合成数据后端基线。**
本次未提交报告、未推送、未合并 PR、未创建标签，等待中期版本冻结指令。
