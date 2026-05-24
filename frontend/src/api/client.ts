import axios, { AxiosError } from "axios";
import { message } from "antd";
import { useAuth } from "../store/auth";

export const http = axios.create({
  baseURL: "/api",
  timeout: 15_000,
});

http.interceptors.request.use((cfg) => {
  const token = useAuth.getState().token;
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

http.interceptors.response.use(
  (resp) => resp,
  (err: AxiosError<any>) => {
    const status = err.response?.status;
    const detail = err.response?.data?.detail;
    if (status === 401) {
      useAuth.getState().clear();
      message.error("登录已过期，请重新登录");
      if (location.pathname !== "/login") location.href = "/login";
    } else if (status === 403) {
      message.error("当前角色无权进行该操作");
    } else if (detail) {
      message.error(typeof detail === "string" ? detail : JSON.stringify(detail));
    } else {
      message.error(err.message || "请求失败");
    }
    return Promise.reject(err);
  }
);

export interface PagedResult<T> {
  total: number;
  page: number;
  size: number;
  items: T[];
}
