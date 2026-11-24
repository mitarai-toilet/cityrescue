# 东南大学四牌楼校区路线演示

本目录包含从 OpenStreetMap 提取的校内道路选段，覆盖南门内侧的中央大道、大礼堂南侧环路、南高路和东门内侧的群贤路。包含 45 个道路节点、50 条路段和 1 个建筑轮廓。学校官网用于确认校区及地标，坐标和道路拓扑来自 OpenStreetMap。

## 来源和许可

- 版权 © OpenStreetMap contributors。此目录的 OpenStreetMap 提取数据及其派生路网按 [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) 发布。展示地图或路线时请在图旁保留 [OpenStreetMap 署名](https://www.openstreetmap.org/copyright)。
- 来源为 2026-11-24 下载的 [OSM API 地图切片](https://api.openstreetmap.org/api/0.6/map?bbox=118.7849,32.0528,118.7923,32.0600)（SHA-256 `7dfa9ad09c1535cb518398298ae5a8272633fb60c4afa84227406700dbeffa03`）和 [校区边界关系](https://www.openstreetmap.org/relation/16272607) v3。用该关系检查选段位于校区内。地标参见 [东南大学校区介绍](https://cis.seu.edu.cn/hwenglish/2024/0628/c54341a495841/page.htm) 和 [大礼堂介绍](https://law.seu.edu.cn/2024/1213/c56755a514720/page.htm)。
- `SPL-N<id>` 引用 OSM 节点，`SPL-R<way>-<from>-<to>` 引用同一条 OSM way 的相邻节点。下表列出的 way 只选择 `highway=service` 且没有显式机动车限制的路段。同坐标未共享 OSM 节点的道路保持各自的拓扑。长度按 WGS84 端点间的球面距离计算，演示车速统一为估算的 15 km/h。

| OSM way | 版本 | 取段 |
| --- | --- | --- |
| [237022770](https://www.openstreetmap.org/way/237022770) | 8 | 中央大道 |
| [479464934](https://www.openstreetmap.org/way/479464934) | 3 | 中央大道至南门内侧，节点 2450172906 至 9711162066 |
| [237057065](https://www.openstreetmap.org/way/237057065) | 4 | 中央大道西侧连接路 |
| [236879446](https://www.openstreetmap.org/way/236879446) | 6 | 南高路 |
| [237022771](https://www.openstreetmap.org/way/237022771) | 3 | 大礼堂南侧环路 |
| [237022772](https://www.openstreetmap.org/way/237022772) | 4 | 群贤路西段 |
| [236879445](https://www.openstreetmap.org/way/236879445) | 10 | 群贤路东段，东门内侧节点 9708723656 至 2449059364 |
| 236946073、236946074、236946069、237063305 | 6、7、7、5 | 校内连接路 |
| [236944775](https://www.openstreetmap.org/way/236944775) | 3 | 大礼堂建筑轮廓 |

空间数据标记为 `real`，校区的 `verified` 为 `false`，现场通行权限、道路宽度和车辆可达性待校方或 A 岗核验。样例任务位置只挂接到实际路网节点，车辆、事件、灾害状态和通行基线均为演示设定。目标节点位于大礼堂南侧道路，建筑入口和室内区域超出数据范围。

## 启动和复跑

在仓库根目录运行。

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.sipailou_app:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m pytest -q tests/test_sipailou_dispatch.py
```

使用 `GET /api/v1/campus/graph` 核对 `campus_id=SEU-SIPAILOU-OSM`，然后通过 `POST /api/v1/simulation/runs` 创建 `SPL-FLOOD-DEMO` 运行。提交本目录下的第一辆车和第一个事件到 `POST /api/v1/dispatch`，即可计算从南门内侧到大礼堂南侧的路线。人工封闭 `SPL-R237022770-2449059357-2450052111` 后，用新版本再次派车运行绕行。API 请求及版本规则见 [D 岗调度模块交付](../../../docs/D_DISPATCH.md)。

| 实测算法输出 | 路线 | 长度 | 估算 ETA |
| --- | --- | ---: | ---: |
| 基线状态 | 南门内侧 → 中央大道 → 大礼堂南侧 | 243.10 米 | 0.97 分钟 |
| 指定路段封闭 | 南门内侧 → 中央大道 → 西侧连接路 → 南高路 → 大礼堂南侧 | 405.66 米 | 1.62 分钟 |

地震固定样例关闭同一路段，得到相同绕行结果。地图上的两条路线均由上述实际路段拼接。版本冲突及两车三任务由 `tests/test_sipailou_dispatch.py` 验证。
