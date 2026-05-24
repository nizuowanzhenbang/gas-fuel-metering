import { useEffect, useState } from "react";
import { Button, Card, Drawer, Select, Space, Table, Tag, message } from "antd";
import dayjs from "dayjs";
import { Alert, ackAlert, listAlerts, resolveAlert } from "../api/resources";
import { useAuth } from "../store/auth";

const LEVEL_COLOR: Record<string, string> = { INFO: "blue", WARN: "orange", CRITICAL: "red" };
const STATUS_COLOR: Record<string, string> = { OPEN: "red", ACKED: "blue", RESOLVED: "green" };

export default function AlertsPage() {
  const [items, setItems] = useState<Alert[]>([]);
  const [filters, setFilters] = useState<{ level?: string; status?: string }>({ status: "OPEN" });
  const [active, setActive] = useState<Alert | null>(null);
  const [loading, setLoading] = useState(false);
  const role = useAuth((s) => s.role);
  const canDispatch = role !== "VIEWER";

  const fetch = async () => {
    setLoading(true);
    try {
      const r = await listAlerts({ ...filters, size: 200 });
      setItems(r.items);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    fetch();
  }, [filters]);

  const doAck = async (id: number) => {
    await ackAlert(id);
    message.success("已认领");
    fetch();
  };
  const doResolve = async (id: number) => {
    await resolveAlert(id);
    message.success("已处置");
    fetch();
  };

  return (
    <Card
      title="告警中心"
      extra={
        <Space>
          <Select
            allowClear
            placeholder="等级"
            style={{ width: 120 }}
            options={["INFO", "WARN", "CRITICAL"].map((v) => ({ value: v }))}
            value={filters.level}
            onChange={(v) => setFilters({ ...filters, level: v })}
          />
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 120 }}
            options={["OPEN", "ACKED", "RESOLVED"].map((v) => ({ value: v }))}
            value={filters.status}
            onChange={(v) => setFilters({ ...filters, status: v })}
          />
        </Space>
      }
    >
      <Table
        rowKey="id"
        dataSource={items}
        loading={loading}
        pagination={{ pageSize: 20 }}
        columns={[
          { title: "告警号", dataIndex: "alert_no", width: 180 },
          { title: "等级", dataIndex: "level", width: 90, render: (v) => <Tag color={LEVEL_COLOR[v]}>{v}</Tag> },
          { title: "分类", dataIndex: "category", width: 200 },
          { title: "描述", dataIndex: "message" },
          { title: "状态", dataIndex: "status", width: 100, render: (v) => <Tag color={STATUS_COLOR[v]}>{v}</Tag> },
          { title: "发生时间", dataIndex: "opened_at", width: 160, render: (v) => dayjs(v).format("MM-DD HH:mm:ss") },
          {
            title: "操作",
            width: 220,
            fixed: "right",
            render: (_, row) => (
              <Space>
                <Button size="small" onClick={() => setActive(row)}>详情</Button>
                {canDispatch && row.status === "OPEN" && (
                  <Button size="small" type="primary" onClick={() => doAck(row.id)}>认领</Button>
                )}
                {canDispatch && row.status !== "RESOLVED" && (
                  <Button size="small" onClick={() => doResolve(row.id)}>处置</Button>
                )}
              </Space>
            ),
          },
        ]}
      />

      <Drawer open={!!active} onClose={() => setActive(null)} title={active?.alert_no} width={520}>
        {active && (
          <Space direction="vertical" style={{ width: "100%" }}>
            <p>
              <Tag color={LEVEL_COLOR[active.level]}>{active.level}</Tag>
              <Tag color={STATUS_COLOR[active.status]}>{active.status}</Tag>
              <span>{active.category}</span>
            </p>
            <p>{active.message}</p>
            <p>站点：{active.station_id ?? "-"} ｜ GC：{active.gc_id ?? "-"} ｜ 气源：{active.source_id ?? "-"}</p>
            <p>发生：{dayjs(active.opened_at).format("YYYY-MM-DD HH:mm:ss")}</p>
            {active.acked_at && <p>认领：{dayjs(active.acked_at).format("YYYY-MM-DD HH:mm:ss")}</p>}
            {active.resolved_at && <p>处置：{dayjs(active.resolved_at).format("YYYY-MM-DD HH:mm:ss")}</p>}
            {active.payload_json && (
              <pre style={{ background: "#fafafa", padding: 12 }}>{JSON.stringify(active.payload_json, null, 2)}</pre>
            )}
          </Space>
        )}
      </Drawer>
    </Card>
  );
}
