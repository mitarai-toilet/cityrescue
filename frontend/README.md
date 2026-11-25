# CITYRESCUE 九龙湖校区演练

## 本地启动

需要 Node.js、npm 和已安装仓库根目录 `requirements.txt` 的 Python 环境。页面使用本地 OpenStreetMap 数据绘制九龙湖校区。启用演练后，车辆、求救点、路况和路线叠加在同一个地图画布上。演练图层可以隐藏，地图视角会保留。

在仓库根目录准备 D 的后端。若已建立对应 worktree，可直接使用。

```powershell
rtk git fetch origin
rtk proxy git worktree add --detach ../cityrescue-backend e49dfb2
rtk proxy .\.venv\Scripts\python.exe frontend/reference/serve_exercise.py --backend ../cityrescue-backend
```

启动器将九龙湖演练数据传给 D 分支现有的 FastAPI 和 NetworkX 实现，监听 `127.0.0.1:8002`。另开终端，在 `frontend/` 运行：

```powershell
rtk npm ci
rtk npm run dev -- --host 127.0.0.1
```

打开 [调度工作台](http://127.0.0.1:5173/)。如需更换后端端口，给启动器传 `--port`，并在启动 Vite 前设置 `$env:CITYRESCUE_API_URL`。Vite 的 `/api` 代理仅适用于开发模式，部署静态站点时需配置同源 API。

## 演练

1. 启动洪涝情景，载入三项演示任务，再点击「调度待处理任务」。地图上会显示两辆车的路线，还有一项任务待分配。
2. 在 `JL-E1 · JL-V2` 的结果内点击「开始执行」。保持车辆确认节点不变，在「查看路线上的路段」中选择第二段 `JL-R300165443-36`。
3. 右侧「道路管制」会选中该路段。点击「封闭道路」，再点击「重规划 JL-E1」。同一辆车会绕开该路段，ETA 从 **2.07** 分钟更新为 **3.57** 分钟。蓝色实线表示当前路线，深色虚线表示旧路线。
4. 可继续添加任务、标记执行任务完成并释放车辆。切换到地震情景时，页面会要求确认是否清除本标签页的演练记录。

道路几何和长度来自 OpenStreetMap，路网覆盖指定校区范围内可连通的部分道路。演练采用统一假设车速 24 km/h，灾情、临时封路位置及车辆和求救点均为模拟。道路条件、校内车辆权限和校区数据尚未线下核验。台账仅在当前标签页保存，调度后端重启后需要启动新运行。详见 [地图数据来源](reference/README.md)。

## 验收

从仓库根目录运行。测试使用真实 FastAPI 和 NetworkX，验证底图与演练图层共用画布、路段几何来自 OSM，以及首次调度、追加任务、同车封路绕行、不可达、版本冲突和同步恢复。

```powershell
rtk proxy npx.cmd --yes --package @playwright/cli@0.1.25 playwright-cli -s=cityrescue-b-regression open http://127.0.0.1:5173/ --browser=msedge
rtk proxy npx.cmd --yes --package @playwright/cli@0.1.25 playwright-cli -s=cityrescue-b-regression run-code --filename frontend/checks/dispatch.browser.js
rtk proxy npx.cmd --yes --package @playwright/cli@0.1.25 playwright-cli -s=cityrescue-b-regression close
```

打开页面的 URL 后可加 `?capture` 重拍 [校区底图](../output/playwright/cityrescue-b-campus.png)、[首次调度](../output/playwright/cityrescue-b-before.png) 和 [封路重规划](../output/playwright/cityrescue-b-after.png)。
