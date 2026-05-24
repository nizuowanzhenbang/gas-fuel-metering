import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Role = "ADMIN" | "OPERATOR" | "METER_ENG" | "ACCOUNTANT" | "VIEWER";

interface AuthState {
  token: string | null;
  username: string | null;
  role: Role | null;
  setAuth: (token: string, username: string, role: Role) => void;
  clear: () => void;
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      username: null,
      role: null,
      setAuth: (token, username, role) => set({ token, username, role }),
      clear: () => set({ token: null, username: null, role: null }),
    }),
    { name: "gfm-auth" }
  )
);

export const ROLE_LABELS: Record<Role, string> = {
  ADMIN: "管理员",
  OPERATOR: "运行值班",
  METER_ENG: "计量工程师",
  ACCOUNTANT: "财务结算",
  VIEWER: "数据浏览",
};
