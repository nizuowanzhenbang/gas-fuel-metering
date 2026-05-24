import { useEffect, useState } from "react";
import { Button, Card, DatePicker, Form, Input, InputNumber, message, Modal, Select, Space, Table, Tag } from "antd";
import dayjs from "dayjs";
import { PlusOutlined } from "@ant-design/icons";
import { GasSource, MeteringStation, createStation, listGasSources, listStations, updateStation } from "../api/resources";
import { useAuth } from "../store/auth";

const STATUS_COLOR: Record<string, string> = { RUNNING: "green", MAINTENANCE: "orange", OFFLINE: "default" };

export default function StationsPage() {
  const [items, setItems] = useState<MeteringStation[]>([]);
  const [sources, setSources] = useState<GasSource[]>([]);
  const [editing, setEditing] = useState<MeteringStation | null>(null);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const role = useAuth((s) => s.role);
  const canWrite = role === "ADMIN" || role === "METER_ENG";

  const fetch = async () => {
    const [a, b] = await Promise.all([listStations({ size: 200 }), listGasSources({ size: 200 })]);
    setItems(a.items);
    setSources(b.items);
  };
  useEffect(() => {
    fetch();
  }, []);

  const onAdd = () => {
    setEditing(null);
    form.resetFields();
    setOpen(true);
  };
  const onEdit = (row: MeteringStation) => {
    setEditing(row);
    form.setFieldsValue({ ...row, verified_until: row.verified_until ? dayjs(row.verified_until) : null });
    setOpen(true);
  };
  const onSubmit = async () => {
    const v = await form.validateFields();
    const body = {
      ...v,
      verified_until: v.verified_until ? v.verified_until.toISOString() : null,
    };
    if (editing) {
      await updateStation(editing.id, body);
      message.success("已更新");
    } else {
      await createStation(body);
      message.success("已新增");
    }
    setOpen(false);
    fetch();
  };

  const sourceMap = new Map(sources.map((s) => [s.id, s.code]));

  return (
    <Card
      title="计量站档案"
      extra={canWrite && <Button icon={<PlusOutlined />} type="primary" onClick={onAdd}>新增</Button>}
    >
      <Table
        rowKey="id"
        dataSource={items}
        pagination={{ pageSize: 20 }}
        columns={[
          { title: "编号", dataIndex: "code", width: 100 },
          { title: "名称", dataIndex: "name" },
          { title: "气源", dataIndex: "source_id", width: 120, render: (v) => v ? sourceMap.get(v) : "-" },
          { title: "设计压力(kPa)", dataIndex: "design_pressure_kpa", width: 130 },
          { title: "设计流量(Nm³/h)", dataIndex: "design_flow_max_nm3h", width: 140, render: (_, r) => `${r.design_flow_min_nm3h}–${r.design_flow_max_nm3h}` },
          {
            title: "检定到期",
            dataIndex: "verified_until",
            width: 140,
            render: (v) => {
              if (!v) return "-";
              const days = dayjs(v).diff(dayjs(), "day");
              return <Tag color={days < 30 ? "red" : days < 60 ? "orange" : "default"}>{dayjs(v).format("YYYY-MM-DD")}</Tag>;
            },
          },
          {
            title: "状态",
            dataIndex: "status",
            width: 100,
            render: (v) => <Tag color={STATUS_COLOR[v]}>{v}</Tag>,
          },
          {
            title: "操作",
            width: 100,
            fixed: "right",
            render: (_, row) =>
              canWrite ? <Button size="small" onClick={() => onEdit(row)}>编辑</Button> : null,
          },
        ]}
      />

      <Modal open={open} onCancel={() => setOpen(false)} onOk={onSubmit} title={editing ? `编辑 ${editing.code}` : "新增计量站"} destroyOnClose>
        <Form form={form} layout="vertical">
          {!editing && (
            <Form.Item label="编号" name="code" rules={[{ required: true, pattern: /^MS-\d{2}$/, message: "格式 MS-NN" }]}>
              <Input placeholder="MS-01" />
            </Form.Item>
          )}
          <Form.Item label="名称" name="name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label="位置" name="location"><Input /></Form.Item>
          <Form.Item label="所属气源" name="source_id" rules={[{ required: true }]}>
            <Select options={sources.map((s) => ({ value: s.id, label: `${s.code} ${s.name}` }))} />
          </Form.Item>
          <Form.Item label="设计压力 (kPa)" name="design_pressure_kpa" rules={[{ required: true }]}>
            <InputNumber min={0} style={{ width: "100%" }} step={10} />
          </Form.Item>
          <Form.Item label="设计流量下限 (Nm³/h)" name="design_flow_min_nm3h" rules={[{ required: true }]}>
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item label="设计流量上限 (Nm³/h)" name="design_flow_max_nm3h" rules={[{ required: true }]}>
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item label="检定到期日" name="verified_until"><DatePicker style={{ width: "100%" }} /></Form.Item>
          {editing && (
            <Form.Item label="状态" name="status">
              <Select options={[{ value: "RUNNING" }, { value: "MAINTENANCE" }, { value: "OFFLINE" }]} />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </Card>
  );
}
