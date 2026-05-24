import { useEffect, useState } from "react";
import { Button, Card, Form, Input, InputNumber, message, Modal, Popconfirm, Select, Space, Table, Tag } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import {
  GasSource,
  createGasSource,
  listGasSources,
  retireGasSource,
  updateGasSource,
} from "../api/resources";
import { useAuth } from "../store/auth";

const STATUS_COLOR: Record<string, string> = { ACTIVE: "green", SUSPENDED: "orange", RETIRED: "default" };

export default function GasSourcesPage() {
  const [items, setItems] = useState<GasSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<GasSource | null>(null);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const role = useAuth((s) => s.role);
  const canWrite = role === "ADMIN" || role === "METER_ENG";

  const fetch = async () => {
    setLoading(true);
    try {
      const r = await listGasSources({ size: 200 });
      setItems(r.items);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    fetch();
  }, []);

  const onAdd = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ gas_type: "PIPELINE", supplier: "中石油" });
    setOpen(true);
  };

  const onEdit = (row: GasSource) => {
    setEditing(row);
    form.setFieldsValue(row);
    setOpen(true);
  };

  const onSubmit = async () => {
    const v = await form.validateFields();
    if (editing) {
      await updateGasSource(editing.id, v);
      message.success("已更新");
    } else {
      await createGasSource(v);
      message.success("已新增");
    }
    setOpen(false);
    fetch();
  };

  return (
    <Card
      title="气源档案"
      extra={
        canWrite && (
          <Button icon={<PlusOutlined />} type="primary" onClick={onAdd}>
            新增气源
          </Button>
        )
      }
    >
      <Table
        rowKey="id"
        dataSource={items}
        loading={loading}
        pagination={{ pageSize: 20 }}
        columns={[
          { title: "编号", dataIndex: "code", width: 100 },
          { title: "名称", dataIndex: "name" },
          { title: "供应方", dataIndex: "supplier", width: 100 },
          { title: "类型", dataIndex: "gas_type", width: 80 },
          { title: "合同号", dataIndex: "contract_no", width: 180 },
          { title: "基准价(元/Nm³)", dataIndex: "contract_base_price", width: 140 },
          { title: "日计划(Nm³)", dataIndex: "daily_volume_plan_nm3", width: 140, render: (v) => v?.toLocaleString() },
          {
            title: "状态",
            dataIndex: "status",
            width: 90,
            render: (v) => <Tag color={STATUS_COLOR[v]}>{v}</Tag>,
          },
          {
            title: "操作",
            width: 180,
            fixed: "right",
            render: (_, row) =>
              canWrite ? (
                <Space>
                  <Button size="small" onClick={() => onEdit(row)}>
                    编辑
                  </Button>
                  {row.status !== "RETIRED" && (
                    <Popconfirm
                      title="软删除该气源？编号不可复用"
                      onConfirm={async () => {
                        await retireGasSource(row.id);
                        fetch();
                      }}
                    >
                      <Button size="small" danger>
                        停用
                      </Button>
                    </Popconfirm>
                  )}
                </Space>
              ) : null,
          },
        ]}
      />

      <Modal
        open={open}
        title={editing ? `编辑 ${editing.code}` : "新增气源"}
        onCancel={() => setOpen(false)}
        onOk={onSubmit}
        destroyOnClose
      >
        <Form layout="vertical" form={form}>
          {!editing && (
            <Form.Item label="编号" name="code" rules={[{ required: true, pattern: /^SRC-\d{3}$/, message: "格式 SRC-NNN" }]}>
              <Input placeholder="SRC-001" />
            </Form.Item>
          )}
          <Form.Item label="名称" name="name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item label="供应方" name="supplier" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "中石油" },
                { value: "中石化" },
                { value: "中海油" },
                { value: "LNG 接收站" },
              ]}
            />
          </Form.Item>
          <Form.Item label="类型" name="gas_type" rules={[{ required: true }]}>
            <Select options={[{ value: "PIPELINE", label: "管道气" }, { value: "LNG", label: "LNG 气化" }]} />
          </Form.Item>
          <Form.Item label="合同号" name="contract_no"><Input /></Form.Item>
          <Form.Item label="基准价（元/Nm³）" name="contract_base_price"><InputNumber min={0} style={{ width: "100%" }} step={0.01} /></Form.Item>
          <Form.Item label="日计划量（Nm³）" name="daily_volume_plan_nm3"><InputNumber min={0} style={{ width: "100%" }} /></Form.Item>
          {editing && (
            <Form.Item label="状态" name="status">
              <Select options={[{ value: "ACTIVE" }, { value: "SUSPENDED" }]} />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </Card>
  );
}
