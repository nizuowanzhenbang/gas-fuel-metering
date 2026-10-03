# 数据库版本与升级

本轮替代启动时 `create_all`：应用与 seed 只检查当前版本和结构，不再自动改变表。冻结 `0001_baseline`（第 6 轮原表）→ `0002_archive`（第 7 轮留档表）。迁移文件不导入当前 ORM；未来模型变化需新增迁移及版本契约。

## 本地流程（仓库根目录）

配置 `DATABASE_URL` 后执行：

```bash
python -m backend.migrate upgrade
python -m backend.migrate check
python -m backend.seed_data
uvicorn backend.main:app --port 8010
```

upgrade 接受空数据库，以及两种精确已知的未标版本数据库：完整基础表、完整基础表加留档表。对已有库先比对列、类型、可空性、默认值、主外键、索引、唯一约束及检查约束，拒绝非基线视图/触发器；通过后标记相应版本，再升级。未知结构、未知/空/多条版本记录拒绝，不自动猜测、修复或删除数据。该检查不是对所有数据库权限、扩展、RLS 或物理存储属性的安全审计。

SQLite 使用 BEGIN IMMEDIATE；PostgreSQL 16 使用事务及迁移专用 advisory lock，串行化本迁移命令。本轮仅验收 PostgreSQL 16；索引目录检查使用 15+ 的属性，不支持更老版本。锁不阻止应用业务写入，部署升级时必须停止写入。命令不输出连接串或原始数据库异常参数。check 检查缺失 SQLite 文件时不创建该文件。

## 已有部署

1. 停止 backend 及其他写入者，记录代码版本；备份数据库。备份需在独立数据库验证后才作为恢复依据。
2. 用新代码和相同 DATABASE_URL 执行 upgrade；失败时保留原数据库，分析具体结构差异，禁止强行 stamp。
3. check 成功后启动；抽查历史归档哈希、重放与父子关联。

Compose 新增一次性 migrate 服务，成功后才启动 backend。已有 Compose 部署先停写，再执行 `docker compose build backend migrate`、`docker compose run --rm migrate`，成功后 `docker compose up -d`。本轮没有在本机执行 Docker 验收；远程独立 PostgreSQL job 验证数据库行为。

## 回退与演示数据

两次迁移均为新增结构，代码回退到第 7 轮时保留版本表和留档表即可；不要 DROP 留档表。自动 downgrade 被禁用，需要数据回退时恢复已验证备份到独立数据库再切换连接。此轮测试了事务失败回滚，不等于备份恢复演练。

`seed_data --reset` 沿用原来的破坏性演示重置行为，现在要求数据库已迁移且通过结构检查，然后删除并重建业务表；会清空留档和业务数据。日常演示使用不带 reset 的 seed 命令。禁止对需要保留数据的库执行 reset。

## 测试边界

```bash
python -m pytest backend/tests --ignore=backend/tests/postgresql -q
# 设置 TEST_POSTGRESQL_URL 为独立 PostgreSQL 测试库，库名必须以 _test 结尾。
# CI 另设置 REQUIRE_POSTGRESQL_TESTS=true，缺配置失败，没有 SQLite 回退。
python -m pytest backend/tests/postgresql -q -o addopts=''
```

每个 PostgreSQL 测试新建随机 `gfm_test_...` schema，结束只清理该 schema。覆盖空库/旧库升级、重复执行、结构漂移拒绝、迁移故障整体回滚、历史留档接纳后跨连接重放，以及子记录写入失败不残留。读数与用户名均为合成测试数据；未证明生产吞吐或任意并发场景。

设计参考：[Alembic 官方连接共享与事务](https://alembic.sqlalchemy.org/en/latest/cookbook.html#sharing-a-connection-across-one-or-more-programmatic-migration-commands)，2026-10-03 核对。
