import { Button, Card, Form, Input, message, Typography } from "antd";
import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { login } from "../api/auth";
import { useAuth } from "../store/auth";

export default function LoginPage() {
  const nav = useNavigate();
  const setAuth = useAuth((s) => s.setAuth);

  const onFinish = async (v: { username: string; password: string }) => {
    try {
      const resp = await login(v.username, v.password);
      setAuth(resp.access_token, resp.username, resp.role);
      message.success(`欢迎，${resp.username}`);
      nav("/dashboard");
    } catch {
      /* 拦截器已 toast */
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "linear-gradient(135deg, #0958d9 0%, #003a8c 100%)",
      }}
    >
      <Card style={{ width: 400 }}>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          燃气燃料计量 v1.0
        </Typography.Title>
        <Typography.Text type="secondary" style={{ display: "block", marginBottom: 24 }}>
          燃气电厂燃料计量与气源管理系统
        </Typography.Text>
        <Form layout="vertical" onFinish={onFinish} initialValues={{ username: "admin", password: "demo123" }}>
          <Form.Item name="username" rules={[{ required: true, message: "请输入用户名" }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: "请输入密码" }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>
            登录
          </Button>
        </Form>
        <Typography.Paragraph type="secondary" style={{ marginTop: 16, fontSize: 12 }}>
          演示账号：admin / operator / engineer / accountant / viewer，密码均为 demo123
        </Typography.Paragraph>
      </Card>
    </div>
  );
}
