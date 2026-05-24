# TASK.md

> v0.1 ~ v0.3 任务清单。完成的项目用 `✅`，进行中用 `🚧`，未启动留空。

## v1.0 · 项目骨架与核心算法（**已完成**）

### 文档

- [x] ✅ README.md 业务设计文档
- [x] ✅ CLAUDE.md 开发约定与术语
- [x] ✅ TASK.md 本文件
- [x] ✅ .gitignore（Python + Node 标准模板）

### 后端骨架

- [x] ✅ backend/ 目录初始化（pyproject.toml + requirements.txt + .env.example）
- [x] ✅ main.py（FastAPI 实例 + CORS + lifespan + scheduler 接入）
- [x] ✅ database.py（SQLAlchemy 2.x + Session 工厂 + init_db）
- [x] ✅ auth.py（JWT 签发与校验 + 5 角色 RBAC + 跨系统暗号校验，bcrypt 原生）
- [x] ✅ config.py（pydantic-settings，环境变量集中读取，enable_scheduler 开关）
- [x] ✅ models/users.py
- [x] ✅ models/gas_sources.py
- [x] ✅ models/metering_stations.py
- [x] ✅ models/gc_analyzers.py
- [x] ✅ models/metering_readings.py（含 validity 字段）
- [x] ✅ models/gc_readings.py
- [x] ✅ models/settlement_records.py
- [x] ✅ models/alerts.py
- [x] ✅ schemas/ Pydantic 全覆盖（auth / users / 档案三件套 / readings / reconciliation / alerts）

### 核心算法（必须有单元测试）

- [x] ✅ utils/pressure_temp_compensation.py
  - [x] ✅ 基础温压补偿（GB/T 22634 公式）
  - [x] ✅ Z 因子查表法（双线性插值 + 边界夹断，v0.2 升级 AGA8）
  - [x] ✅ 单元测试：8 个用例
- [x] ✅ utils/heating_value.py
  - [x] ✅ HHV / LHV 计算（GB/T 11062，7 主组分 + others）
  - [x] ✅ Wobbe 指数 + 密度 + 相对密度
  - [x] ✅ 单元测试：8 个用例
- [x] ✅ utils/reconciliation.py
  - [x] ✅ 日 0.5% / 月 0.3% / 主备 0.3% 三档判定
  - [x] ✅ 单元测试：8 个用例
- [x] ✅ utils/numbering.py（AL-YYYYMMDD-NNNN / SETTLE-YYYYMM-NN 编号生成）

### 路由（最小可用集）

- [x] ✅ routers/auth.py（OAuth2 表单登录，返回 JWT）
- [x] ✅ routers/users.py（账户 CRUD，仅 ADMIN）
- [x] ✅ routers/gas_sources.py（CRUD + 软删除）
- [x] ✅ routers/metering_stations.py（CRUD + 关联校验 + 软停用）
- [x] ✅ routers/gc_analyzers.py（CRUD + 关联校验 + 软停用）
- [x] ✅ routers/readings.py（计量分钟级 + GC 组分；POST 自动算法回填）
- [x] ✅ routers/reconciliation.py（日对账 + 主备回路对账）
- [x] ✅ routers/upload.py（上游日报 Excel 批量导入，行级容错）
- [x] ✅ routers/alerts.py（查询 + OPEN→ACKED→RESOLVED 状态机）
- [x] ✅ routers/dashboard.py（实时大屏聚合 overview + station 快照）

### 跨系统与服务层

- [x] ✅ services/integration_client.py（httpx + 3s 超时 + 2 次指数退避 + 暗号头）
- [x] ✅ services/alerting.py（告警写入 helper，按 category+对象去重）

### 调度任务（APScheduler）

- [x] ✅ scheduler.py
  - [x] ✅ 每日 06:00 触发昨日主备回路自查
  - [x] ✅ 每日 08:00 扫描计量设备检定到期（30 天预警）
  - [x] ✅ 每分钟扫描主备计量偏差（1 小时窗口）
  - [x] ✅ 每 5 分钟扫描 GC 校准状态与故障

### Seed 数据

- [x] ✅ seed_data.py（5 角色 + 3 气源 + 2 站 + 2 GC + 24h × 5min 读数 + 24h GC + 2 结算 + 3 告警）

### 前端

- [x] ✅ Vite + React + TS + Ant Design + ECharts + Zustand 骨架
- [x] ✅ 登录页 + JWT 持久化 + 路由守卫
- [x] ✅ 实时大屏（4×2 KPI + ECharts 6h 流量趋势 + 站点快照表）
- [x] ✅ 档案管理（气源 / 计量站 / GC）
- [x] ✅ 对账中心（手动日对账 + Excel 拖拽导入 + 行级判定表）
- [x] ✅ 告警中心（筛选 + 详情抽屉 + ack / resolve 处置）
- [x] ✅ 用户管理（CRUD + 重置密码 + 软停用）

### 部署

- [x] ✅ Dockerfile（backend / frontend 各一份）
- [x] ✅ docker-compose.yml（postgres + backend + frontend，端口 8010 / 5180）
- [x] ✅ .env.example（生产覆盖 JWT_SECRET / INTEGRATION_SECRET / ADMIN_PASSWORD）

### 测试

- [x] ✅ 24 个算法单测（温压补偿 / 热值 / 对账）
- [x] ✅ 67 个 router 集成测试（auth / users / 档案三件套 / readings / reconciliation / alerts / upload / dashboard）
- [x] ✅ 6 个调度任务单测（不启动 scheduler 直接调用 job 函数）
- [x] ✅ **总计 97 测试全过**

---

## v0.2 · 月对账闭环 + 跨系统联动

- [ ] 月结算单完整生命周期（草稿 → 已对账 → 已审批 → 已结算 → 归档）
- [ ] 月对账界面（厂内 vs 上游月单的对比 + 差异图表）
- [ ] 简化 AGA8 数值实现（替代查表法）
- [ ] 跨系统：调用 gas-turbine-performance 拉燃机出力，计算实时热效率
- [ ] 跨系统：调用 fuel-procurement 拉气源合同基准
- [ ] 跨系统：调用 equipment-inspection 拉计量设备健康度
- [ ] 跨系统：向 emission-monitoring 提供气质组分接口
- [ ] 跨系统：管网压力异常自动推送 plant-safety
- [ ] WebSocket 实时大屏推送
- [ ] 告警移动端推送（基于 PWA）

---

## v0.3 · 自动化与生产化

- [ ] 上游日报自动接入（解析中石油 / 中石化的标准格式邮件或 API）
- [ ] 完整 AGA8 / SGERG 算法
- [ ] DCS 直连（OPC UA / Modbus TCP）
- [ ] 边缘网关接入（计量站本地缓存，断网续传）
- [ ] 检定管理推送到 equipment-inspection 形成闭环
- [ ] 时序数据迁移到 TimescaleDB
- [ ] 多机组场景：支持 2x1、3x1 联合循环架构

---

## 历史变更

- 2026-05-23：v0.1 文档三件套完成，仓库创建（仅文档，无代码）
- 2026-05-24：v0.1 第一刀 —— 后端骨架 + 8 张 ORM 表 + 温压补偿 + 热值计算 + 档案 schema，16 单测
- 2026-05-24：v0.1 第二刀 —— utils/reconciliation.py 三件套收尾，+8 单测，累计 24 单测
- 2026-05-24：v0.1 第三刀 —— routers/auth + 档案三件套 CRUD + ensure_default_admin + conftest + 17 集成测试，累计 41 测试
- 2026-05-24：v0.1 第四刀 —— routers/readings.py 时序写入 + 算法回填，+8 集成测试，累计 49 测试
- 2026-05-25：**v1.0 收官** —— users + reconciliation + alerts + upload + dashboard 5 个路由收尾，scheduler 4 类定时任务，integration_client 跨系统封装，seed_data 演示数据集，前端 7 个页面 + Vite/AntD/ECharts/Zustand 全栈，Dockerfile + docker-compose，bcrypt 切原生 API，**累计 97 测试全过**

---

## 开发约束（给后续 Claude）

1. **不在用户本地部署运行** —— 所有验证靠代码 review 和 unit test，**不要主动 docker compose up / npm run dev**
2. **算法模块必须有单元测试** —— 温压补偿、热值、对账三件套，没有测试不算完成
3. **跨系统调用必须经过 `services/integration_client.py`** —— 不允许散落的 httpx 调用
4. **PRIVATE 仓库** —— 默认 `gh repo create --private`，不需要再问
5. **v0.2 起每次会话只啃 1-2 个模块** —— 避免一次性写满整个版本，单次提交内容可控
