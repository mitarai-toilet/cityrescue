# CITYRESCUE AI v0.1 数据契约冻结记录

- 版本：v0.1
- 状态：已冻结，供团队开发与联调使用
- 冻结日期：2026-11-22（Asia/Shanghai）
- 唯一正式实体规范：`contracts/schemas/*.schema.json`，11 类实体
- 聚合入口：`contracts/schema_v0_1.json`，通过 `$ref` 引用正式实体 Schema
- 聚合样例：`contracts/sample_v0_1.json`，统一采用新字段
- 固定数据：`data/fixtures/synthetic_campus/`，全部为合成占位数据

## 字段与兼容性

道路统一使用 `from_node`、`to_node`，风险惩罚使用 `risk_penalty_min`（分钟）。
旧 `risk_cost` 未定义单位，禁止自动转换或编造换算系数；当前样例使用已标注的合成值。
完整迁移差异见 [MIGRATION_v0_1.md](MIGRATION_v0_1.md)。

## 实际验收

三个修改过的专项测试文件均通过 `python -m py_compile`。

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_contracts.py tests/test_fixture_integrity.py tests/test_schema_validation.py
```

本次实际结果：**24 passed in 0.62s**，0 failed，0 skipped。
覆盖离线聚合引用解析、11 类实体 Schema、固定实体实例、必填/类型/枚举负例、
ID 引用和独立图连通情景。详细报告见 [测试报告](../docs/v0.1_freeze_test_report.md)。

## 已知限制与验收边界

- `Scenario.params` 内部灾种参数尚未细化校验。
- 建筑多边形几何完整性尚未全面验证。
- `ExplainResult` 证据存在性需业务层校验。
- 后端旧状态版本拦截尚未验收；快照版本递增只证明样例数据变化。
- ASGI 健康自动化测试本次已执行，运行阶段超时；问题修复继续暂缓。
- 契约冻结不代表正式调度、真实校园数据或全系统通过验收。

## 冻结后变更

字段修改必须通过 PR，同时更新 Schema、fixtures、测试和说明，由涉及成员评审、队长批准。
破坏兼容性的修改必须显式升级契约版本。冻结基线以本记录所在 Git 提交为准。

## 五人联调入口

- A：按实体 Schema 提供 Campus、Node、Road、Building，补充真实数据来源与许可。
- B：读取 fixtures 空间数据、RoadState、DispatchResult 绘制 MapLibre 地图。
- C：读取 Scenario 与空间资产，输出 RoadState、BuildingState。
- D：读取 Road、RoadState、Vehicle、Event，输出 DispatchResult。
- E：负责 API 编排、状态版本管理，并基于计算证据生成 ExplainResult。
