import { Avatar, Dropdown, Layout, Menu, Tag, theme } from "antd";
import {
  AlertOutlined,
  ApiOutlined,
  BarChartOutlined,
  DashboardOutlined,
  ExperimentOutlined,
  LogoutOutlined,
  TeamOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth, ROLE_LABELS } from "../store/auth";

const { Header, Sider, Content } = Layout;

const MENU = [
  { key: "/dashboard", icon: <DashboardOutlined />, label: "实时大屏" },
  { key: "/gas-sources", icon: <ApiOutlined />, label: "气源档案" },
  { key: "/stations", icon: <ExperimentOutlined />, label: "计量站" },
  { key: "/gcs", icon: <ExperimentOutlined />, label: "色谱仪" },
  { key: "/reconciliation", icon: <BarChartOutlined />, label: "对账中心" },
  { key: "/alerts", icon: <AlertOutlined />, label: "告警中心" },
  { key: "/users", icon: <TeamOutlined />, label: "用户管理", admin: true },
];

export default function AppLayout() {
  const nav = useNavigate();
  const loc = useLocation();
  const { username, role, clear } = useAuth();
  const { token } = theme.useToken();

  const items = MENU.filter((m) => !m.admin || role === "ADMIN").map(({ key, icon, label }) => ({
    key,
    icon,
    label,
  }));

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider width={220} style={{ background: token.colorBgContainer }}>
        <div
          style={{
            padding: "20px 16px",
            fontWeight: 700,
            fontSize: 16,
            color: token.colorPrimary,
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
          }}
        >
          燃气燃料计量
          <div style={{ fontSize: 12, color: token.colorTextSecondary, fontWeight: 400, marginTop: 4 }}>
            Gas Fuel Metering v1.0
          </div>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[loc.pathname]}
          items={items}
          onClick={({ key }) => nav(key)}
          style={{ borderInlineEnd: "none" }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: token.colorBgContainer,
            padding: "0 24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
          }}
        >
          <div style={{ fontSize: 16, color: token.colorTextSecondary }}>
            燃气电厂燃料计量与气源管理系统
          </div>
          <Dropdown
            menu={{
              items: [
                {
                  key: "logout",
                  icon: <LogoutOutlined />,
                  label: "退出登录",
                  onClick: () => {
                    clear();
                    nav("/login");
                  },
                },
              ],
            }}
          >
            <div style={{ display: "flex", gap: 8, alignItems: "center", cursor: "pointer" }}>
              <Avatar icon={<UserOutlined />} size="small" />
              <span>{username}</span>
              {role && <Tag color="blue">{ROLE_LABELS[role]}</Tag>}
            </div>
          </Dropdown>
        </Header>
        <Content style={{ padding: 24, background: "#f5f5f5" }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
