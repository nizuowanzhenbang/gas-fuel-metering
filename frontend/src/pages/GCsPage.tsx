import { useEffect, useState } from "react";
import { Button, Card, DatePicker, Form, Input, message, Modal, Select, Table, Tag } from "antd";
import dayjs from "dayjs";
import { PlusOutlined } from "@ant-design/icons";
import { GCAnalyzer, MeteringStation, createGC, listGCs, listStations, updateGC } from "../api/resources";
import { useAuth } from "../store/auth";

const STATUS_COLOR: Record<string, string> = { RUNNING: "green", CALIBRATING: "blue", FAULT: "red", OFFLINE: "default" };

export default function GCsPage() {
  const [items, setItems] = useState<GCAnalyzer[]>([]);
  const [stations, setStations] = useState<MeteringStation[]>([]);
  const [editing, setEditing] = useState<GCAnalyzer | null>(null);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const role = useAuth((s) => s.role);
  const canWrite = role === "ADMIN" || role === "METER_ENG";

  const fetch = async () => {
    const [a, b] = await Promise.all([listGCs({ size: 200 }), listStations({ size: 200 })]);
    setItems(a.items);
    setStations(b.items);
  };
  useEffect(() => {
    fetch();
  }, []);

  const onSubmit = async () => {
    const v = await form.validateFields();
    const body = {
      ...v,
      last_calibration_at: v.last_calibration_at ? v.last_calibration_at.toISOString() : null,
      next_calibration_at: v.next_calibration_at ? v.next_calibration_at.toISOString() : null,
    };
    if (editing) {
      await updateGC(editing.id, body);
      message.success("已更新");
    } else {
      await createGC(body);
      message.success("已新增");
    }
    setOpen(false);
    fetch();
  };

  const stationMap = new Map(stations.map((s) => [s.id, s.code]));

  return (
    <Card
      title="色谱仪档案"
      extra={
        canWrite && (
          <Button
            icon={<PlusOutlined />}
            type="primary"
            onClick={() => {
              setEditing(null);
              form.resetFields();
              setOpen(true);
            }}
          >
            新增
          </Button>
        )
      }
    >
      <Table
        rowKey="id"
        dataSource={items}
        pagination={{ pageSize: 20 }}
        columns={[
          { title: "编号", dataIndex: "code", width: 100 },
          { title: "型号", dataIndex: "model" },
          { title: "出厂编号", dataIndex: "serial_no", width: 160 },
          { title: "归属计量站", dataIndex: "station_id", width: 130, render: (v) => v ? stationMap.get(v) : "-" },
          { title: "上次校准", dataIndex: "last_calibration_at", width: 140, render: (v) => v ? dayjs(v).format("YYYY-MM-DD") : "-" },
          {
            title: "下次校准",
            dataIndex: "next_calibration_at",
            width: 140,
            render: (v) => {
              if (!v) return "-";
              const days = dayjs(v).diff(dayjs(), "day");
              return <Tag color={days < 7 ? "red" : days < 30 ? "orange" : "default"}>{dayjs(v).format("YYYY-MM-DD")}</Tag>;
            },
          },
          { title: "状态", dataIndex: "status", width: 100, render: (v) => <Tag color={STATUS_COLOR[v]}>{v}</Tag> },
          {
            title: "操作",
            width: 100,
            fixed: "right",
            render: (_, row) =>
              canWrite ? (
                <Button
                  size="small"
                  onClick={() => {
                    setEditing(row);
                    form.setFieldsValue({
                      ...row,
                      last_calibration_at: row.last_calibration_at ? dayjs(row.last_calibration_at) : null,
                      next_calibration_at: row.next_calibration_at ? dayjs(row.next_calibration_at) : null,
                    });
                    setOpen(true);
                  }}
                >
                  编辑
                </Button>
              ) : null,
          },
        ]}
      />

      <Modal open={open} onCancel={() => setOpen(false)} onOk={onSubmit} title={editing ? `编辑 ${editing.code}` : "新增色谱仪"} destroyOnClose>
        <Form form={form} layout="vertical">
          {!editing && (
            <Form.Item label="编号" name="code" rules={[{ required: true, pattern: /^GC-\d{2}$/, message: "格式 GC-NN" }]}>
              <Input placeholder="GC-01" />
            </Form.Item>
          )}
          <Form.Item label="型号" name="model" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label="出厂编号" name="serial_no"><Input /></Form.Item>
          <Form.Item label="归属计量站" name="station_id">
            <Select allowClear options={stations.map((s) => ({ value: s.id, label: `${s.code} ${s.name}` }))} />
          </Form.Item>
          <Form.Item label="上次校准" name="last_calibration_at"><DatePicker style={{ width: "100%" }} /></Form.Item>
          <Form.Item label="下次校准" name="next_calibration_at"><DatePicker style={{ width: "100%" }} /></Form.Item>
          {editing && (
            <Form.Item label="状态" name="status">
              <Select options={["RUNNING", "CALIBRATING", "FAULT", "OFFLINE"].map((v) => ({ value: v }))} />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </Card>
  );
}
