import { useEffect, useState } from "react";
import { Button, Card, Form, Input, message, Modal, Popconfirm, Select, Space, Switch, Table, Tag } from "antd";
import { LockOutlined, PlusOutlined } from "@ant-design/icons";
import { UserRow, createUser, deactivateUser, listUsers, resetUserPassword, updateUser } from "../api/resources";
import { ROLE_LABELS } from "../store/auth";

export default function UsersPage() {
  const [items, setItems] = useState<UserRow[]>([]);
  const [open, setOpen] = useState(false);
  const [pwdOpen, setPwdOpen] = useState<UserRow | null>(null);
  const [editing, setEditing] = useState<UserRow | null>(null);
  const [form] = Form.useForm();
  const [pwdForm] = Form.useForm();

  const fetch = async () => {
    const r = await listUsers({ size: 200 });
    setItems(r.items);
  };
  useEffect(() => {
    fetch();
  }, []);

  const onSubmit = async () => {
    const v = await form.validateFields();
    if (editing) {
      await updateUser(editing.id, v);
      message.success("已更新");
    } else {
      await createUser(v);
      message.success("已新增");
    }
    setOpen(false);
    fetch();
  };

  const onReset = async () => {
    const v = await pwdForm.validateFields();
    await resetUserPassword(pwdOpen!.id, v.password);
    message.success("已重置密码");
    setPwdOpen(null);
    pwdForm.resetFields();
  };

  return (
    <Card
      title="用户管理"
      extra={
        <Button
          icon={<PlusOutlined />}
          type="primary"
          onClick={() => {
            setEditing(null);
            form.resetFields();
            form.setFieldsValue({ role: "VIEWER" });
            setOpen(true);
          }}
        >
          新增账户
        </Button>
      }
    >
      <Table
        rowKey="id"
        dataSource={items}
        pagination={{ pageSize: 20 }}
        columns={[
          { title: "用户名", dataIndex: "username", width: 140 },
          { title: "姓名", dataIndex: "full_name", width: 140 },
          { title: "角色", dataIndex: "role", width: 140, render: (v) => <Tag color="blue">{ROLE_LABELS[v as keyof typeof ROLE_LABELS]}</Tag> },
          { title: "状态", dataIndex: "is_active", width: 100, render: (v) => v ? <Tag color="green">启用</Tag> : <Tag>停用</Tag> },
          {
            title: "操作",
            width: 260,
            render: (_, row) => (
              <Space>
                <Button
                  size="small"
                  onClick={() => {
                    setEditing(row);
                    form.setFieldsValue(row);
                    setOpen(true);
                  }}
                >
                  编辑
                </Button>
                <Button size="small" icon={<LockOutlined />} onClick={() => setPwdOpen(row)}>重置密码</Button>
                {row.is_active && (
                  <Popconfirm title="停用该账户？" onConfirm={async () => { await deactivateUser(row.id); fetch(); }}>
                    <Button size="small" danger>停用</Button>
                  </Popconfirm>
                )}
              </Space>
            ),
          },
        ]}
      />

      <Modal open={open} onCancel={() => setOpen(false)} onOk={onSubmit} title={editing ? `编辑 ${editing.username}` : "新增账户"} destroyOnClose>
        <Form form={form} layout="vertical">
          {!editing && (
            <>
              <Form.Item label="用户名" name="username" rules={[{ required: true, min: 3, pattern: /^[A-Za-z0-9_.-]+$/ }]}>
                <Input />
              </Form.Item>
              <Form.Item label="密码" name="password" rules={[{ required: true, min: 6 }]}>
                <Input.Password />
              </Form.Item>
            </>
          )}
          <Form.Item label="姓名" name="full_name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label="角色" name="role" rules={[{ required: true }]}>
            <Select options={Object.entries(ROLE_LABELS).map(([v, l]) => ({ value: v, label: l }))} />
          </Form.Item>
          {editing && (
            <Form.Item label="启用" name="is_active" valuePropName="checked"><Switch /></Form.Item>
          )}
        </Form>
      </Modal>

      <Modal open={!!pwdOpen} onCancel={() => setPwdOpen(null)} onOk={onReset} title={`重置 ${pwdOpen?.username} 的密码`} destroyOnClose>
        <Form form={pwdForm} layout="vertical">
          <Form.Item label="新密码" name="password" rules={[{ required: true, min: 6 }]}>
            <Input.Password />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
