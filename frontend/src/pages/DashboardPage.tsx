import { useEffect, useMemo, useState } from "react";
import { Card, Col, Row, Spin, Statistic, Table, Tag } from "antd";
import ReactECharts from "echarts-for-react";
import dayjs from "dayjs";
import { getOverview, getStationSnapshots, listMeteringReadings, Overview, StationSnapshot } from "../api/resources";

const LEVEL_COLOR: Record<string, string> = { INFO: "blue", WARN: "orange", CRITICAL: "red" };
const STATUS_COLOR: Record<string, string> = { RUNNING: "green", MAINTENANCE: "orange", OFFLINE: "default" };

export default function DashboardPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [snapshots, setSnapshots] = useState<StationSnapshot[]>([]);
  const [trend, setTrend] = useState<{ ts: string; rate: number }[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const tick = async () => {
      try {
        const [o, s] = await Promise.all([getOverview(), getStationSnapshots()]);
        setOverview(o);
        setSnapshots(s);
        if (s.length > 0) {
          const tsFrom = dayjs().subtract(6, "hour").toISOString();
          const r = await listMeteringReadings({
            station_id: s[0].station_id,
            ts_from: tsFrom,
            size: 200,
          });
          setTrend(
            r.items
              .slice()
              .reverse()
              .map((i) => ({ ts: dayjs(i.ts).format("HH:mm"), rate: i.normal_volume_rate_nm3h }))
          );
        }
      } finally {
        setLoading(false);
      }
    };
    tick();
    const t = window.setInterval(tick, 30_000);
    return () => window.clearInterval(t);
  }, []);

  const chartOption = useMemo(
    () => ({
      grid: { left: 60, right: 24, top: 30, bottom: 40 },
      xAxis: { type: "category", data: trend.map((p) => p.ts) },
      yAxis: { type: "value", name: "Nm³/h" },
      tooltip: { trigger: "axis" },
      series: [
        {
          name: "标方流量",
          type: "line",
          smooth: true,
          areaStyle: { opacity: 0.15 },
          data: trend.map((p) => p.rate),
        },
      ],
    }),
    [trend]
  );

  return (
    <Spin spinning={loading}>
      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Statistic title="活跃气源" value={overview?.active_sources ?? 0} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="运行计量站" value={overview?.running_stations ?? 0} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="近 24h 气量 (Nm³)"
              value={overview?.last_24h_volume_nm3 ?? 0}
              precision={0}
              groupSeparator=","
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="最新 HHV (MJ/Nm³)"
              value={overview?.latest_hhv_mj_nm3 ?? "-"}
              precision={overview?.latest_hhv_mj_nm3 ? 3 : 0}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic title="在线 GC" value={overview?.online_gc ?? 0} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="未处置告警 (CRITICAL)"
              value={overview?.open_alerts.critical ?? 0}
              valueStyle={{ color: "#cf1322" }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="未处置告警 (WARN)"
              value={overview?.open_alerts.warn ?? 0}
              valueStyle={{ color: "#d46b08" }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="30 天内检定到期" value={overview?.verification_due_30d ?? 0} />
          </Card>
        </Col>
      </Row>

      <Card title="首站近 6 小时标方流量" style={{ marginTop: 16 }}>
        {trend.length ? (
          <ReactECharts option={chartOption} style={{ height: 280 }} />
        ) : (
          <div style={{ padding: 32, textAlign: "center", color: "#999" }}>暂无读数</div>
        )}
      </Card>

      <Card title="计量站实时快照" style={{ marginTop: 16 }}>
        <Table
          rowKey="station_id"
          dataSource={snapshots}
          size="middle"
          pagination={false}
          columns={[
            { title: "编号", dataIndex: "code", width: 80 },
            { title: "名称", dataIndex: "name" },
            { title: "气源", dataIndex: "source_code", width: 100 },
            {
              title: "状态",
              dataIndex: "status",
              width: 100,
              render: (v) => <Tag color={STATUS_COLOR[v]}>{v}</Tag>,
            },
            {
              title: "标方流量(Nm³/h)",
              dataIndex: "latest_normal_volume_rate_nm3h",
              width: 140,
              render: (v) => (v == null ? "-" : v.toLocaleString()),
            },
            {
              title: "压力(kPa)",
              dataIndex: "latest_pressure_kpa",
              width: 100,
              render: (v) => (v == null ? "-" : v.toFixed(2)),
            },
            {
              title: "温度(℃)",
              dataIndex: "latest_temperature_c",
              width: 90,
              render: (v) => (v == null ? "-" : v.toFixed(1)),
            },
            {
              title: "累计(Nm³)",
              dataIndex: "accumulated_volume_nm3",
              width: 140,
              render: (v) => (v == null ? "-" : Math.round(v).toLocaleString()),
            },
            {
              title: "HHV(MJ/Nm³)",
              dataIndex: "latest_hhv_mj_nm3",
              width: 120,
              render: (v) => (v == null ? "-" : v.toFixed(3)),
            },
            {
              title: "未处置最高级",
              dataIndex: "last_alert_level",
              width: 120,
              render: (v) => (v ? <Tag color={LEVEL_COLOR[v]}>{v}</Tag> : "-"),
            },
            {
              title: "更新时间",
              dataIndex: "latest_ts",
              width: 160,
              render: (v) => (v ? dayjs(v).format("MM-DD HH:mm:ss") : "-"),
            },
          ]}
        />
      </Card>
    </Spin>
  );
}
