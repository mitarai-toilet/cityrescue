# 东南大学四牌楼校区 · 灾害仿真

场景 ID 为 SPL-flood 与 SPL-earthquake，校区 ID 为 SEU-SPL。覆盖大礼堂、孟芳图书馆周边教学片区。两栋建筑及路网几何取自 © OpenStreetMap contributors，空间数据库依 [ODbL](https://www.openstreetmap.org/copyright) 提供。学校对地标的介绍见[四牌楼校区简介](https://splgwh.seu.edu.cn/25023/list.htm)。

地图提取窗口为 WGS84 [118.7870,32.0556,118.7910,32.0592]。从公开地图的 service 道路中按原始节点切段，保留片区内连通的 75 个节点和 88 段道路。路段 ID 含 OSM way 编号与原线段序号，建筑 ID 含 OSM way 编号。道路速度统一假设为 15 km/h，出入口、道闸、车辆准入与实地尺寸尚待现场核验。

## 使用

解压后运行 `python verify.py` 可复验全部固定输出与绕行路径。运行 `python hazard.py flood.input.json local.json` 可重新生成洪涝快照。将 spl_campus 目录交给团队后端，在 feature/C-hazard 版本使用 `create_app(data_directory=d, simulation_provider=CProvider(d))`，其中 d 是该目录的 pathlib.Path。后端入口发布最后一个对齐步长的快照，离线输出包含全部 7 帧。

## 场景与验收

洪涝以 80 毫米/小时持续 60 分钟，等效排水 10 毫米/小时。中央大道选定路段汇水倍率设为 5，其余为 1。水深为 max(0, 雨强 × 汇水倍率 − 排水强度) × 历时分钟 / 60000 米。0.10 米起警戒，0.30 米起禁行。建筑按邻近路段的积水等级作暴露代理。

地震情景直接指定演练封路清单，大礼堂设为中等情景风险，孟芳图书馆设为未知。道路水深为 null。两类风险和绕行结果仅用于课程演练，参数未经现场标定。

已实际执行 verify.py --backend。两个情景的固定输出可复现，每帧均通过仓库 RoadState 和 BuildingState 校验，后端均成功创建第 60 分钟快照。第 50 分钟选定路段封闭，detour.json 给出端点及 8 段连续可通行的替代路线，已检查方向与禁行标记。此项为 C 侧验收。
