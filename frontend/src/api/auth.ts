import { http } from "./client";
import type { Role } from "../store/auth";

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in_minutes: number;
  username: string;
  role: Role;
}

export async function login(username: string, password: string): Promise<TokenResponse> {
  const body = new URLSearchParams();
  body.append("username", username);
  body.append("password", password);
  const { data } = await http.post<TokenResponse>("/auth/login", body, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  return data;
}
