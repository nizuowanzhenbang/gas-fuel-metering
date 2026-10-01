# 燃气电厂燃料计量与气源管理系统

## 求职展示更新：对账数据质量与计算依据

日对账要求配置业务日的首末边界（默认UTC零点），逐站检查缺数、计数器回退和重复时间；主备回路必须区间一致。API、Excel 与定时扫描共用检查逻辑，页面展示逐站计算依据。旧数据不满足条件时返回 409，详见[接口变化与面试演示](docs/INTERVIEW.md)。

> 一座燃气电厂每天烧掉的天然气价值上百万，**这笔钱怎么算清楚** —— 跟谁买的气、热值多少、流量准不准、月底跟上游对账有没有差异 —— 是这套系统要回答的全部问题。
>
> 本项目是 [智慧火电厂全链路管理平台](https://github.com/nizuowanzhenbang/smart-power-plant) 的 **燃气电厂线** 第一个子系统，对应燃煤线的 [煤炭采购+运输监督+煤质化验] 三合一位置。
>
> **当前版本：v1.0** —— 后端 (FastAPI + 8 ORM + 9 路由 + APScheduler 4 类任务 + 跨系统调用)、前端 (Vite + React + TS + Ant Design + ECharts + Zustand)、Docker Compose 部署 全部落地，**97 个测试全部通过**。

---

## 一、它解决什么问题

一座 F 级燃气电厂（单机 350MW 量级），一台燃机满负荷运行 **每小时烧掉约 5 万 Nm³ 天然气**。按门站价 3 元/Nm³ 估算，**一小时燃料成本 15 万元**，一天满发就是 360 万元，一个月一台机 1 亿出头。

钱这么大，但是燃气电厂的燃料管理有几个跟燃煤完全不同的现实：

- **燃料从管道直接接进来**，没有车、没有过磅、没有堆场、没有库龄 —— 燃煤厂那套"运输监督 + 入场化验 + 煤场库存"用不上；
- **热值实时变化**：管道气可能来自西气东输（甲烷含量 95%+）、俄气、进口 LNG 气化（甲烷含量 99%+）、或本地页岩气，**不同气源混输时热值在 30-38 MJ/Nm³ 区间漂移**，每 MJ/Nm³ 的偏差直接影响结算单价；
- **上游不是一家**：中石油（西气）、中石化（川气）、中海油（LNG）任意两家或三家同时供气是常态，**每家一套计量、一套合同、一套结算口径**；
- **计量不能停**：燃气厂没有缓冲库存，**计量站一旦故障，机组立即被迫降负荷甚至停机**，损失按分钟计；
- **月度对账压力大**：厂内累计计量 vs 上游公司日报单 vs 月结算单，**三方数据必须对得上**，差 0.5% 月底就是上百万的争议。

**问题来了**：传统模式下，运行值班员用 Excel 抄表、抄温压、抄热值，财务用纸单子跟上游公司对账，发现差异往往是 30 天以后 —— **钱已经流出去了才知道差**。

**这套系统要做的事**：把"管道气进厂 → 实时计量 → 热值在线分析 → 月度结算对账"全链路用同一套数字流程串起来，每一步都自动记录、任何偏差实时报警、跟上游的差异每天都能看清楚。

---

## 二、一管气的完整旅程

整套系统讲的就是这一件事 —— 一立方天然气从上游管道进入厂界到烧进燃机的全过程：

```
①上游计量交接          ②厂内计量站            ③GC 在线分析            ④进入燃机
   │                       │                      │                      │
   ▼                       ▼                      ▼                      ▼
中石油/中石化           计量站（流量计/         GC 色谱仪每分钟          燃机消耗，
日报数据                 压力变送器/             更新组分 + 热值          调用燃机系统
                         温度变送器）            （HHV / LHV / Wobbe）   拉实时出力
   │                       │                      │                      │
   │                       └── 温压补偿 ─► 标准状态体积流量（Nm³）       │
   │                                                                       │
   │                                          ⑤实时热效率 = 出力 / (流量 × HHV)
   │                                                                       │
   ▼                                                                       │
日 / 月对账：厂内累计 vs 上游日报 vs 月结算单 ◄────────────────────────────┘
   │
   ▼
差异 > 0.5% 自动告警 → 调度 / 财务 / 计量班三方介入复核
```

整个过程对运行人员来说只是"系统在自动记账"，对系统来说是一条 **每分钟更新的精算流水线**。

---

## 三、核心业务模块

### 3.1 气源与计量站管理

**做什么**：维护所有上游气源（哪家公司、什么合同、设计供气量、计量交接点位置）和厂内计量站（流量计型号、计量精度、设计能力、检定周期）的档案。

**关键点**：
- 一个气源对应一家上游公司、一份合同；一份合同对应一套结算单价机制（固定价 / 联动价 / 阶梯价）
- 一个计量站可以同时接收多个气源（混输），也可以专属某一路气源
- 流量计有两种主流型号：超声波流量计（精度 0.5%）、气体涡轮流量计（精度 1.0%）；不同型号的不确定度直接影响计量公允性
- 计量站检定周期：流量计 2 年、温压变送器 1 年，**到期未检定的计量数据法律上不认可**

### 3.2 实时计量与温压补偿

**做什么**：每分钟从计量站采集瞬时流量、压力、温度，按 **GB/T 22634《天然气流量积算系统》** 做温压补偿，得到标准状态下的体积流量（Nm³）。

**为什么必须补偿**：流量计直接测出来的是 **工况体积**（管道内实际温压下的体积），但天然气计量结算统一用 **标准状态体积**（20℃、101.325 kPa）。**夏冬温差能让同一立方气的真实质量差 10% 以上**，不补偿就是赔钱送气。

**核心公式**（详见第六章）：
```
Q_n = Q_w × (P_w / P_n) × (T_n / T_w) × (Z_n / Z_w)
```

### 3.3 热值在线分析

**做什么**：接入 GC（气相色谱仪）数据，每分钟更新天然气组分（C1 甲烷 / C2 乙烷 / C3 丙烷 / N₂ / CO₂ 等）和对应的高位热值（HHV）、低位热值（LHV）、Wobbe 指数。

**为什么重要**：
- **结算价格按 HHV 计价**：合同里写"基准热值 38 MJ/Nm³，每偏差 1% 单价相应调整"，没有实时热值就没法精准结算；
- **燃机控制看 Wobbe 指数**：Wobbe 指数变化 ±5% 燃机控制系统就要重新整定燃料阀，否则可能熄火或超温；
- **环保排放跟组分相关**：CH₄ 含量高 NOx 多，CO₂ 含量高热值低 —— 这部分会推给 [emission-monitoring](https://github.com/nizuowanzhenbang/emission-monitoring) 做预警。

### 3.4 与上游气源公司的对账

**做什么**：每天自动拉取中石油 / 中石化 / 中海油的日计量数据（通过对方提供的接口或 Excel 导入），跟厂内当日累计做对比；月底拉月结算单跟厂内月累计对比。

**三方对账逻辑**：
```
                    厂内累计计量
                   （A：自家流量计 + GC + 温压补偿）
                          │
                          │
   上游日报 ────────►  对比 ◄────────  月结算单
   （B：上游日报）                    （C：上游月单）
                          │
                          ▼
           |A - B| / A ?  日偏差容差：0.5%
           |A - C| / A ?  月偏差容差：0.3%
                          │
                          ▼
              超容差 → 告警 + 三方复核流程
```

**为什么这一步关键**：传统方式月底才发现差异，**钱已经付出去了**；自动对账每天滚动比对，**任何异常 24 小时内浮现**，财务和计量班能及时拿证据找上游协商。

### 3.5 管网监控与告警

**做什么**：盯着管网入厂段的压力、流量、计量站状态，异常实时告警。

**典型告警类型**：
- **压力骤降**：上游管线压力突降可能是上游故障，机组要做好降负荷准备
- **压力骤升**：调压橇故障或下游阀异常，安全风险
- **流量突变**：与机组当前负荷不匹配（机组没变工况但流量大幅波动）
- **GC 异常**：色谱仪故障或组分异常（甲烷突然降到 80% 以下要警惕掺气）
- **计量超差**：A/B 两套计量回路（主备）读数差超过 0.3%
- **检定超期**：流量计或变送器超过检定周期

### 3.6 能耗匹配与热效率分析

**做什么**：把"耗气量 × HHV"和燃机实时出力关联，算出每台机组的实时热效率（kJ/kWh），跟厂家保证值和合同保证值比对。

**为什么这是核心 KPI**：
- 燃机厂家会写"在 ISO 工况下保证净效率 38%"，但厂里实际值取决于环境温度、出力、气质、设备健康
- 实时热效率连续下降可能意味着燃机性能衰减（待 [gas-turbine-performance](https://github.com/nizuowanzhenbang/gas-turbine-performance) 系统建成后做深度分析）
- **每降 0.1% 热效率，一台机一年多烧的气价值大几百万**

---

## 四、数据模型

### 8 张核心表

| 表名 | 主要字段 | 用途 |
|---|---|---|
| `users` | 5 角色：ADMIN / OPERATOR / METER_ENG（计量工程师）/ ACCOUNTANT（财务）/ VIEWER | 账户体系 |
| `gas_sources` | 编号 `SRC-NNN`、上游公司、合同号、设计供气量、单价机制 | 气源档案 |
| `metering_stations` | 编号 `MS-NN`、设计能力、流量计型号、计量精度、检定到期日 | 计量站档案 |
| `gc_analyzers` | 编号 `GC-NN`、所属站、组分范围、校准周期 | GC 色谱仪档案 |
| `metering_readings` | 分钟级时序：瞬时流量、压力、温度、累计流量、补偿后 Nm³ | 计量主流水 |
| `gc_readings` | 分钟级时序：C1-C6 组分 / N₂ / CO₂ / HHV / LHV / Wobbe | 组分主流水 |
| `settlement_records` | 编号 `SETTLE-YYYYMM-NN`、厂内累计、上游日报累计、月结算单、差异、状态 | 结算对账 |
| `alerts` | 编号 `AL-YYYYMMDD-NNNN`、类型、严重度、处置链路 | 告警闭环 |

### 业务编号规范

| 编号 | 格式 | 用途 |
|---|---|---|
| 气源 | `SRC-001` ~ `SRC-NNN` | 上游气源唯一标识 |
| 计量站 | `MS-01` ~ `MS-NN` | 厂内计量站 |
| GC | `GC-01` ~ `GC-NN` | 色谱仪 |
| 计量批次 | `GAS-YYYYMMDD-NNNN` | 按日切分的批次（用于结算追溯） |
| 月结算 | `SETTLE-YYYYMM-NN` | 月度结算单 |
| 告警 | `AL-YYYYMMDD-NNNN` | 告警唯一标识 |

### 状态机

**计量站**：`COMMISSIONING → ACTIVE → MAINTENANCE → CALIBRATION_DUE → DECOMMISSIONED`

**结算记录**：`DRAFT → RECONCILED（厂内/上游已对账）→ DISPUTED（有争议）→ APPROVED → SETTLED（已付款）→ ARCHIVED`

**告警**：`OPEN → ACKNOWLEDGED → HANDLING → RESOLVED → CLOSED`

---

## 五、跨系统协作

继承火电厂双线总览的"暗号通信"模式（详见 [smart-power-plant 总览](https://github.com/nizuowanzhenbang/smart-power-plant)），跨系统调用通过 HTTP + 共享密钥头进行，所有数据库互不强连接。

| 谁调谁 | 方法 | 路径 | 用途 |
|---|---|---|---|
| 本系统 → gas-turbine-performance | GET | `/api/integration/turbine-output?ts=` | 拉燃机实时出力，算热效率 |
| 本系统 → fuel-procurement | GET | `/api/integration/gas-contract?contract_no=` | 拉气源合同基准（合同热值、单价机制） |
| 本系统 → equipment-inspection | GET | `/api/integration/equipment-health?equipment_no=` | 拉计量设备点检状态、检定到期日 |
| emission-monitoring → 本系统 | GET | `/api/integration/gas-composition?ts=` | 拉天然气组分，用于 NOx 预测 |
| 本系统 → plant-safety | POST | `/api/integration/hazards` | 计量站故障 / 管网压力异常自动建隐患 |
| 本系统 → fuel-procurement | POST | `/api/webhook/gas-delivered` | 月度计量数据回写采购系统，推进合同履约 |

**统一约定**：响应壳 `{ code, message, data }`、超时 3 秒、失败降级（不报错由调度器重推）、幂等键防重复。

---

## 六、关键算法

### 6.1 温压补偿（GB/T 22634）

```
Q_n = Q_w × (P_w / P_n) × (T_n / T_w) × (Z_n / Z_w)
```

| 符号 | 含义 | 标准值 |
|---|---|---|
| `Q_n` | 标准状态下的体积流量（Nm³/h） | 待求 |
| `Q_w` | 工况下的体积流量（m³/h） | 流量计直接测量值 |
| `P_w` / `P_n` | 工况 / 标准状态压力（kPa） | `P_n = 101.325` |
| `T_w` / `T_n` | 工况 / 标准状态温度（K） | `T_n = 293.15`（20℃） |
| `Z_w` / `Z_n` | 工况 / 标准状态压缩因子（无量纲） | `Z_n = 1`，`Z_w` 按 AGA8 或 SGERG 算 |

**`Z_w` 求法**：v0.1 用查表法（按压力、温度、组分查 AGA8 表），v0.2 上简化 AGA8 数值计算。

### 6.2 高位热值（HHV）

基于 GC 组分按 GB/T 11062 计算：
```
HHV_mix = Σ (x_i × HHV_i)
```
- `x_i` = 第 i 种组分的摩尔分数（来自 GC）
- `HHV_i` = 第 i 种纯组分的高位热值（MJ/Nm³，查标准表）

主要组分热值参考（MJ/Nm³，20℃、101.325 kPa）：
- CH₄：39.84
- C₂H₆：69.79
- C₃H₈：99.20
- N₂：0（惰性）
- CO₂：0（惰性）

### 6.3 Wobbe 指数

```
W = HHV / √(d)
```
- `d` = 天然气相对密度（相对于空气）

Wobbe 指数表征"等压等开度下通过燃料阀的能量流"。**控制系统看的是 Wobbe，不是 HHV**。

### 6.4 三方对账容差

| 比对 | 容差 | 超容差行为 |
|---|---|---|
| 厂内累计 vs 上游日报（按日） | 0.5% | 告警，建对账争议条目 |
| 厂内累计 vs 上游月结算单（按月） | 0.3% | 告警 + 阻断 SETTLED 状态推进，需三方复核 |
| 主备计量回路（A/B 两套） | 0.3% | 告警 + 计量班介入校验 |

---

## 七、技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| 后端 | **FastAPI** + SQLAlchemy 2 + Pydantic 2 + JWT | 与火电厂平台其他子系统一致 |
| 前端 | **React 18** + TypeScript + Vite + Ant Design 5 + ECharts | 同上 |
| 数据库 | SQLite（开发） / PostgreSQL（生产） | 时序量大时考虑加 TimescaleDB |
| 跨系统调用 | httpx + 共享密钥头 | 沿用 X-Integration-Secret 约定 |
| 实时推送 | WebSocket | 用于实时计量数据流、告警推送 |
| 定时任务 | APScheduler | 用于日对账、月结算、检定到期扫描 |

### v0.1 范围（待实现）

- 气源、计量站、GC 档案管理（CRUD）
- 计量与组分数据接入（HTTP API 接收 + 手动录入双模式）
- 温压补偿引擎（v0.1 用 Z_w 查表法）
- 热值计算与告警判定
- 日对账（上游日报手动导入 Excel）
- Dashboard 实时大屏

### v0.2 / v0.3 规划

- v0.2：AGA8 数值实现、月结算对账闭环、与 gas-turbine-performance 的热效率联动
- v0.3：上游日报自动接入（API / 邮件爬取）、检定管理推送 equipment-inspection、Docker Compose 一键部署

---

## 八、迭代路线

| 模块 | v0.1 | v0.2 | v0.3 |
|---|---|---|---|
| 档案管理 | ✅ 基础 CRUD | + 检定推送 | + OEM 接口对接 |
| 计量数据接入 | ✅ HTTP + Excel | + DCS 直连 | + 边缘网关 |
| 温压补偿 | ✅ 查表法 | + 简化 AGA8 | + 完整 AGA8/SGERG |
| 热值计算 | ✅ GB/T 11062 | + GB/T 11061 替代算法 | — |
| 对账 | ✅ 日对账 | + 月对账 | + 三方对账自动化 |
| 告警 | ✅ 基础类型 | + WebSocket | + 移动端推送 |
| 跨系统 | — | + 燃机性能 / 采购联动 | + 全平台打通 |

---

## 九、设计哲学

**1. 钱要算到分钟。** 燃料成本一小时十几万，**任何超过 1 分钟的盲区都是钱**。所有计量、组分、对账数据按分钟级别留痕。

**2. 三方制衡。** 厂内、上游日报、上游月单 —— **任何一方都不能单方面定结果**，每天滚动对账，差异 24 小时内浮现。

**3. 法定计量优先。** 流量计型号、检定周期、不确定度等级，按 **OIML R137 / JJG 1003 / GB/T 22634** 国家计量法规走，**未检定数据法律上不可结算**，系统层面强制阻断。

**4. 与煤电线共享底座。** 设备点检、安全生产、采购审批走火电厂统一框架（详见 [smart-power-plant 总览](https://github.com/nizuowanzhenbang/smart-power-plant)），**不重复造轮子**。

**5. 失败降级优于级联熔断。** 跨系统调用 3 秒超时，失败不报错由调度器重推；本系统挂了不影响其他子系统继续工作。

**6. 燃气厂业务特化。** 不强求和燃煤线对称 —— 燃气没有"运输/堆场/库龄"业务，本系统就不留这些空字段；专注燃气特有的"管道气计量 + 热值波动 + 三方对账"三件事。

---

## 仓库一览

| 项目 | 角色 | 链接 |
|---|---|---|
| 智慧火电厂双线总览 | 上层平台 | https://github.com/nizuowanzhenbang/smart-power-plant |
| **本仓库** | 燃气线 · 燃料入口 | https://github.com/nizuowanzhenbang/gas-fuel-metering |
| gas-turbine-performance | 燃气线 · 燃机性能（规划中） | — |
| gas-emission-monitoring | 燃气线 · 排放监测（规划中） | — |
| equipment-inspection | 双线共享 · 设备点检 | https://github.com/nizuowanzhenbang/equipment-inspection |
| plant-safety | 双线共享 · 安全生产 | https://github.com/nizuowanzhenbang/plant-safety |
| emission-monitoring | 双线共享 · 环保排放（参数库切换） | https://github.com/nizuowanzhenbang/emission-monitoring |
| fuel-procurement | 框架可复用 · 采购审批 | https://github.com/nizuowanzhenbang/fuel-procurement |

## 十、本地启动 / Docker 部署

### 后端单跑（SQLite，开发用）

```bash
cd backend
python -m venv .venv && source .venv/Scripts/activate     # Windows
pip install -r requirements.txt
python -m backend.seed_data --reset                        # 种入演示数据
uvicorn backend.main:app --port 8010 --reload
# Swagger 文档：http://localhost:8010/docs
```

### 前端单跑（开发热更新）

```bash
cd frontend
npm install
npm run dev   # http://localhost:5180
```

演示账户（密码统一 `demo123`）：

| 用户名 | 角色 | 能做什么 |
|---|---|---|
| admin | ADMIN | 全部 |
| engineer | METER_ENG | 档案 RW、计量录入、对账 |
| operator | OPERATOR | 计量数据录入、告警处置 |
| accountant | ACCOUNTANT | 上游日报上传、对账、结算 |
| viewer | VIEWER | 只读 |

### 一键容器化（PostgreSQL + 后端 + 前端）

```bash
cp .env.example .env       # 改 JWT_SECRET / INTEGRATION_SECRET / ADMIN_PASSWORD
docker compose up -d --build
# 前端 http://localhost:5180  后端 http://localhost:8010
```

容器栈：
- `postgres:16-alpine`（持久卷 `gfm-pg-data`）
- `backend`（uvicorn + APScheduler）
- `frontend`（nginx 静态托管，反代 `/api` 到后端）

---

## 十一、角色权限矩阵（与平台对齐）

| 操作 | ADMIN | METER_ENG | OPERATOR | ACCOUNTANT | VIEWER |
|---|---|---|---|---|---|
| 档案管理（气源 / 站 / GC） | RW | RW | R | R | R |
| 时序读数录入 | RW | RW | RW | — | — |
| 日对账触发 | RW | RW | — | RW | — |
| 上游日报 Excel 上传 | RW | — | — | RW | — |
| 告警处置 | RW | RW | RW | RW | R |
| 用户管理 | RW | — | — | — | — |

---

## 十二、跨系统集成清单

调用方向以本系统为视角，全部经由 `backend/services/integration_client.py`，3 秒超时 + 2 次重试 + `X-Integration-Secret` 头。

| 目标系统 | 方向 | 路径 | 用途 |
|---|---|---|---|
| gas-turbine-performance | OUT GET | `/api/integration/turbine-output` | 拉燃机出力算热效率 |
| fuel-procurement | OUT GET | `/api/integration/gas-contract` | 拉气源合同基准 |
| fuel-procurement | OUT POST | `/api/webhook/gas-delivered` | 月度计量回写 |
| equipment-inspection | OUT GET | `/api/integration/equipment-health` | 拉计量设备点检状态 |
| emission-monitoring | IN GET | `/api/integration/gas-composition` | 提供气质组分 |
| plant-safety | OUT POST | `/api/integration/hazards` | 计量故障 / 管网异常报隐患 |

---

> 本仓库 v1.0 阶段已落地完整后端 + 前端 + Docker，可作为燃气线后续 5 个子系统（gas-turbine-performance / gas-emission-monitoring …）的样板。后续路线见 [TASK.md](TASK.md)。


## 持续维护

[开发与验收说明](docs/MAINTENANCE.md)：自动检查、回归测试与演示边界。

## 业务日配置更新

支持UTC或固定UTC+08:00及分钟级日切；API、Excel、每日扫描共用口径。详见[业务日说明](docs/BUSINESS-DAY.md)。
# 对账留档升级（2026-10-01）

支持显式输入快照、规则版本、历史 JSON 导出、留档重放与关联重算。新结果追加保存，原结果保留；详见 [对账留档与重算](docs/RECONCILIATION-ARCHIVE.md)。当前为可复现原型，不代表财务认证或生产验收。
