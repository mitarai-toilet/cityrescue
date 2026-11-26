# 九龙湖校区地图来源

前端用 OpenStreetMap 的校园及周边区域数据为底图，演练图层叠加在同一张地图上。默认视图定位东南大学九龙湖校区，校区位置可与[学校公布的规划总平面图](https://jbjsc.seu.edu.cn/2025/0630/c44712a534647/page.htm)核对。地图由 MapLibre 在浏览器内渲染，无外部瓦片、字体服务或密钥依赖。

- 地图要素 © OpenStreetMap contributors，数据以 [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) 提供。参见 [OpenStreetMap 数据版权说明](https://www.openstreetmap.org/copyright)。
- 可下载的派生数据见 [jiulonghu.json](../public/maps/jiulonghu.json)。源范围为西 118.804、南 31.880、东 118.826、北 31.901（WGS84），下载日期 2026-11-24。
- 供调度使用的派生道路和节点在 [exercise-data](exercise-data/)，随 ODbL 1.0 提供。演练路网从 OSM 道路按共享节点拆段，保留所选路段的基本单行标记，以坐标计算长度并统一设定 24 km/h 的演练速度。示例灾情、任务和车辆用人工设定的参数。覆盖范围、道路权限、条件通行和实时路况尚未实地核验。
- 底图转换保留指定类型的道路线、建筑、水系、校园、绿地与运动场，并从 OSM 名称中选取部分地标。范围外和部分复杂关系没有完整提取。

从 `frontend/` 更新静态数据：

```powershell
rtk proxy curl.exe --fail -o jiulonghu.osm 'https://api.openstreetmap.org/api/0.6/map?bbox=118.804,31.880,118.826,31.901'
rtk proxy ..\.venv\Scripts\python.exe reference/generate.py jiulonghu.osm public/maps/jiulonghu.json
rtk proxy ..\.venv\Scripts\python.exe reference/generate_exercise.py jiulonghu.osm reference/exercise-data
```
