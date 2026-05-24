# TASK.md

> v0.1 ~ v0.3 任务清单。完成的项目用 `✅`，进行中用 `🚧`，未启动留空。

## v0.1 · 项目骨架与核心算法（当前阶段）

### 文档

- [x] ✅ README.md 业务设计文档
- [x] ✅ CLAUDE.md 开发约定与术语
- [x] ✅ TASK.md 本文件
- [x] ✅ .gitignore（Python + Node 标准模板）

### 后端骨架

- [x] ✅ backend/ 目录初始化（pyproject.toml + requirements.txt + .env.example）
- [x] ✅ main.py（FastAPI 实例 + CORS + lifespan）
- [x] ✅ database.py（SQLAlchemy 2.x + Session 工厂 + init_db）
- [x] ✅ auth.py（JWT 签发与校验 + 5 角色 RBAC + 跨系统暗号校验）
- [x] ✅ config.py（pydantic-settings，环境变量集中读取）
- [x] ✅ models/users.py
- [x] ✅ models/gas_sources.py
- [x] ✅ models/metering_stations.py
- [x] ✅ models/gc_analyzers.py
- [x] ✅ models/metering_readings.py（含 validity 字段）
- [x] ✅ models/gc_readings.py
- [x] ✅ models/settlement_records.py
- [x] ✅ models/alerts.py
- [x] 🚧 schemas/ Pydantic 对应模型（已覆盖：auth + 档案三件套；时序读数/对账/告警 schema 等接入路由时再补）

### 核心算法（必须有单元测试）

- [x] ✅ utils/pressure_temp_compensation.py
  - [x] ✅ 基础温压补偿（GB/T 22634 公式）
  - [x] ✅ Z 因子查表法（双线性插值 + 边界夹断，v0.2 升级 AGA8）
  - [x] ✅ 单元测试：8 个用例，覆盖标准态、网格点、超差、单调性、异常值
- [x] ✅ utils/heating_value.py
  - [x] ✅ HHV / LHV 计算（GB/T 11062，7 主组分 + others）
  - [x] ✅ Wobbe 指数计算 + 密度 + 相对密度
  - [x] ✅ 单元测试：8 个用例，覆盖纯组分、典型管道气、惰性气、容差边界
- [ ] utils/reconciliation.py
  - [ ] 日对账容差判定（0.5%）
  - [ ] 月对账容差判定（0.3%）
  - [ ] 主备计量回路偏差（0.3%）
  - [ ] 单元测试

### 路由（最小可用集）

- [ ] routers/auth.py（登录 / 刷新 token）
- [ ] routers/users.py（账户 CRUD，仅 ADMIN）
- [ ] routers/gas_sources.py（气源档案 CRUD）
- [ ] routers/metering_stations.py（计量站档案 CRUD）
- [ ] routers/gc_analyzers.py（GC 档案 CRUD）
- [ ] routers/readings.py（接收计量+组分数据，HTTP POST）
- [ ] routers/upload.py（上游日报 Excel 导入）
- [ ] routers/reconciliation.py（手动触发日对账）
- [ ] routers/alerts.py（告警查询、处置）
- [ ] routers/dashboard.py（实时大屏聚合接口）

### 调度任务

- [ ] scheduler.py
  - [ ] 每日 06:00 触发昨日对账
  - [ ] 每日 08:00 扫描计量设备检定到期（提前 30 天预警）
  - [ ] 每分钟扫描主备计量偏差
  - [ ] 每 5 分钟扫描 GC 校准状态

### Seed 数据

- [ ] seed_data.py
  - [ ] 5 个角色账号
  - [ ] 3 个气源（西气东输 / 川气东送 / LNG 接收站气化）
  - [ ] 2 个计量站
  - [ ] 2 台 GC
  - [ ] 7 天 × 1 分钟级历史读数（含 1 段超差段、1 段计量故障段）
  - [ ] 1 张已审批结算单 + 1 张草稿

### 前端骨架

- [ ] frontend/ 初始化（Vite + React + TypeScript）
- [ ] 登录页 + 路由守卫
- [ ] 档案管理（气源 / 计量站 / GC）
- [ ] 实时大屏（每个计量站实时流量+压力+温度+HHV）
- [ ] 对账中心（日对账列表 + 差异详情）
- [ ] 告警中心（处置链路）
- [ ] 用户管理

### 部署与文档

- [ ] Dockerfile（backend / frontend 各一份）
- [ ] docker-compose.yml（backend + frontend + postgres + nginx）
- [ ] 默认端口规划：backend 8010 / frontend 5180（避开现有 7 个子系统占用）

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
- 2026-05-24：v0.1 第一刀 —— 后端骨架 + 8 张 ORM 表 + 温压补偿 + 热值计算 + 档案 schema，16 个单测通过（commit feat/v0.1-skeleton）

---

## 开发约束（给后续 Claude）

1. **不在用户本地部署运行** —— 所有验证靠代码 review 和 unit test，**不要主动 docker compose up / npm run dev**
2. **每次会话只啃 1-2 个模块** —— 避免一次性写满整个 v0.1，单次提交内容可控
3. **算法模块必须有单元测试** —— 温压补偿、热值、对账三件套，没有测试不算完成
4. **跨系统调用必须经过 `integration_client.py`** —— 不允许散落的 httpx 调用
5. **PRIVATE 仓库** —— 默认 `gh repo create --private`，不需要再问
