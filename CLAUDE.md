# CLAUDE.md

> 本文件给后续 Claude 会话使用，描述项目定位、技术约定和业务术语，**会话启动时优先读取**。

## 项目定位

- **所属平台**：[智慧火电厂全链路管理平台](https://github.com/nizuowanzhenbang/smart-power-plant) 的 **燃气电厂线**
- **本项目角色**：燃气线 **燃料入口** —— 管道气计量 + 热值在线分析 + 与上游气源公司结算对账
- **对标煤电线**：相当于 coal-transport-monitor + coal-quality-monitor + 部分 fuel-procurement，三合一
- **当前阶段**：v0.1 设计中（仅文档，未实现代码）

## 技术栈基线（与火电厂其他子系统一致）

| 层 | 选型 | 备注 |
|---|---|---|
| 后端 | FastAPI + SQLAlchemy 2.x + Pydantic 2 + JWT | Python 3.11+ |
| 前端 | React 18 + TypeScript + Vite + Ant Design 5 + ECharts + Zustand | Node 18+ |
| 数据库 | SQLite（开发） / PostgreSQL 16（生产） | 时序量大时考虑 TimescaleDB |
| 跨系统 | httpx + `X-Integration-Secret` 头 | 与平台其他子系统统一 |
| 实时推送 | WebSocket（JWT 鉴权） | 实时大屏、告警推送 |
| 定时任务 | APScheduler | 日对账、月结算、检定到期扫描 |
| 文件存储 | 本地（开发） / S3 兼容（生产） | 用于存上游日报/结算单 Excel |

## 目录结构（v0.1 落地后预期）

```
gas-fuel-metering/
├── README.md                  # 业务说明（面向跨专业读者）
├── CLAUDE.md                  # 本文件
├── TASK.md                    # 任务清单 / 路线
├── backend/
│   ├── main.py                # FastAPI 入口
│   ├── database.py            # SQLAlchemy 配置
│   ├── auth.py                # JWT
│   ├── models/                # 8 张表的 ORM 模型
│   ├── schemas/               # Pydantic 模型
│   ├── routers/               # 路由
│   ├── services/              # 业务逻辑（含温压补偿、热值、对账引擎）
│   ├── utils/
│   │   ├── pressure_temp_compensation.py    # GB/T 22634 温压补偿
│   │   ├── heating_value.py                 # GB/T 11062 热值计算
│   │   └── reconciliation.py                # 三方对账
│   ├── scheduler.py           # APScheduler 任务
│   ├── seed_data.py           # 演示数据 seed
│   └── integration_smoke_test.py            # 跨系统冒烟脚本
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── pages/             # 档案管理 / 实时大屏 / 对账 / 告警
│       ├── components/
│       ├── api/
│       └── store/
├── docker-compose.yml
└── .gitignore
```

## 业务术语对照表

跨专业读者较多，**术语必须精准且统一**。

| 术语 | 英文 | 解释 | 同义词 / 易混淆 |
|---|---|---|---|
| 管道气 | pipeline gas | 通过长输管线进厂的天然气 | 区别于 LNG（液化气） |
| LNG | liquefied natural gas | 液化天然气，气化后并入管网 | — |
| 计量站 | metering station | 厂内/界区流量+温压+热值测量的成套设施 | 调压计量橇、调压站 |
| 工况体积 | actual volume (m³) | 流量计直接测量的体积，未做温压补偿 | — |
| 标准状态体积 | normal volume (Nm³) | 20℃、101.325 kPa 下的体积 | 标方、标立方 |
| 温压补偿 | PT compensation | 把工况体积换算到标准状态体积的过程 | — |
| 压缩因子 | compressibility factor Z | 真实气体偏离理想气体的修正系数 | — |
| GC | gas chromatograph | 气相色谱仪，分析天然气组分 | 色谱仪、组分分析仪 |
| HHV | higher heating value | 高位热值，含水蒸气凝结潜热 | 总热值 |
| LHV | lower heating value | 低位热值，不含水蒸气凝结潜热 | 净热值 |
| Wobbe 指数 | Wobbe index | `HHV / √(d)`，控制燃料阀的关键参数 | — |
| 上游 | upstream | 中石油 / 中石化 / 中海油等供气方 | 气源方 |
| 日报 | daily reading | 上游公司每日提供的计量数据 | — |
| 月结算单 | monthly settlement | 月度结算依据 | 结算单、对账单 |
| 三方对账 | three-way reconciliation | 厂内 vs 上游日报 vs 月结算单 | — |
| 检定 | verification | 法定计量器具的强制校准 | 校准、校验（含义不同！） |
| 调压橇 | pressure regulating skid | 把高压气降压到燃机使用压力的撬装设备 | — |

## 开发约定

### 编号规则

| 对象 | 格式 | 示例 |
|---|---|---|
| 气源 | `SRC-NNN` | `SRC-001` |
| 计量站 | `MS-NN` | `MS-01` |
| GC | `GC-NN` | `GC-01` |
| 计量批次 | `GAS-YYYYMMDD-NNNN` | `GAS-20260601-0001` |
| 月结算 | `SETTLE-YYYYMM-NN` | `SETTLE-202606-01` |
| 告警 | `AL-YYYYMMDD-NNNN` | `AL-20260601-0001` |

### 数据精度

- 流量：3 位小数（m³/h / Nm³/h）
- 压力：2 位小数（kPa）
- 温度：1 位小数（℃）
- 热值：3 位小数（MJ/Nm³）
- 累计量：整数（Nm³，月累计可上亿）
- 金额：2 位小数（元）

### 时序数据存储策略

- v0.1：直接存 PostgreSQL，按 `(equipment_id, ts)` 复合索引
- v0.2 若数据量超千万行级：考虑 TimescaleDB 或按月分区
- 任何分钟级时序表必须自带 `validity` 字段（VALID / CALIBRATING / FAULT / SUBSTITUTE），与 emission-monitoring 保持一致

### 跨系统调用规范

- 所有出站调用必须经过 `services/integration_client.py` 包装
- 超时 3 秒，重试 2 次（指数退避 1s / 2s）
- 调用失败不抛错，记录到 `integration_logs` 表由调度器重推
- 鉴权头：`X-Integration-Secret: <env.INTEGRATION_SECRET>`
- 响应格式约定：`{ "code": 200, "message": "ok", "data": {...} }`

### 角色权限矩阵

| 角色 | 档案管理 | 实时计量查看 | 手动录入 | 对账操作 | 结算审批 |
|---|---|---|---|---|---|
| ADMIN | RW | R | RW | RW | RW |
| OPERATOR | R | R | RW | R | — |
| METER_ENG | RW | R | RW | RW | — |
| ACCOUNTANT | R | R | — | RW | RW |
| VIEWER | R | R | — | R | R |

### 测试与验证

- **本项目不在用户本地部署运行**（见用户偏好），所有验证靠代码 review 和 unit test
- 关键算法（温压补偿、热值计算、对账容差）必须有单元测试，**覆盖标准计量例题**
- 跨系统接口写 `integration_smoke_test.py`，但只在 CI 跑

## 跨系统集成清单

| 目标系统 | 调用方向 | 路径 | 用途 |
|---|---|---|---|
| gas-turbine-performance | OUT | `GET /api/integration/turbine-output` | 拉燃机出力算热效率 |
| fuel-procurement | OUT | `GET /api/integration/gas-contract` | 拉气源合同基准 |
| fuel-procurement | OUT | `POST /api/webhook/gas-delivered` | 月度计量回写 |
| equipment-inspection | OUT | `GET /api/integration/equipment-health` | 拉计量设备点检状态 |
| emission-monitoring | IN | `GET /api/integration/gas-composition` | 提供气质组分 |
| plant-safety | OUT | `POST /api/integration/hazards` | 计量故障 / 管网异常报隐患 |

## 不在本项目做的事

明确边界，避免重复造轮子：

- ❌ **燃机性能监控** —— 归 gas-turbine-performance
- ❌ **排放折算与告警** —— 归 emission-monitoring（本系统只提供气质组分）
- ❌ **天然气采购合同与审批** —— 归 fuel-procurement（本系统只读合同基准）
- ❌ **计量设备的点检、缺陷、两票** —— 归 equipment-inspection（本系统只读设备健康度）
- ❌ **管网压力异常的隐患整改** —— 归 plant-safety（本系统只推送）

## 设计哲学（与平台对齐）

1. 数据库相互独立，跨系统用 HTTP + 暗号通信
2. 状态机驱动业务，每次推进可审计
3. 失败降级优于级联熔断
4. 不引入业务无关的中间件（不上 Kafka / Redis）
5. 编号即语义，单据可全链路反查

## 参考标准

- **GB/T 22634** 天然气流量积算系统（温压补偿基本依据）
- **GB/T 11062** 天然气 发热量、密度、相对密度和沃泊指数的计算方法
- **AGA8** 美国煤气协会标准，压缩因子精确计算
- **OIML R137** 国际法制计量组织 气体流量计建议书
- **JJG 1003** 涡轮流量计检定规程
- **DL/T 1755** 燃气-蒸汽联合循环机组性能试验规程

## 给后续 Claude 会话的开发顺序建议

1. 先实现 `models/` 8 张表的 ORM 定义
2. 实现 `utils/pressure_temp_compensation.py` + 单元测试（用 GB/T 22634 例题校验）
3. 实现 `utils/heating_value.py` + 单元测试（用 GB/T 11062 例题校验）
4. 实现档案管理 routers（gas_sources / metering_stations / gc_analyzers）
5. 实现计量与组分数据接入（HTTP API + Excel 导入双模式）
6. 实现 `utils/reconciliation.py` + 日对账 router
7. 前端骨架 + Dashboard
8. 跨系统集成（先与 fuel-procurement 跑通合同基准拉取）

> 每完成一步在 TASK.md 打勾，单一会话不要试图一次写完所有模块。
