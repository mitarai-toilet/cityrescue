# 协作与 Pull Request 规范

## 分支

每位成员从最新 `main` 创建个人功能分支：

- A：`feature/A-data`
- B：`feature/B-frontend`
- C：`feature/C-hazard`
- D：`feature/D-dispatch`
- E（队长）：`feature/E-api`

任务较大时可在个人分支下增加短期子分支。不要直接向 `main` 推送；通过 PR 合并。

## Pull Request

PR 描述需写明目的、改动模块、验证命令及结果、数据来源/许可状态（如涉及），并关联任务。保持 PR 聚焦；请求至少一位队友审阅。由 E 负责集成合并；合并前解决冲突并确认自动检查通过。每日提交可运行片段、测试或截图，并更新阻塞项。

## 接口变更

唯一正式契约位于 `contracts/schemas/`。先更新对应实体 Schema、`data/fixtures/synthetic_campus/` 样例与校验测试，再修改生产/消费模块。`contracts/schema_v0_1.json` 和 `contracts/sample_v0_1.json` 是历史兼容参考，不作为新模块开发依据。PR 必须说明兼容性和迁移影响，并通过契约测试。未经核实的数据不得标作真实；禁止提交 API Key、令牌或本地 `.env`。
