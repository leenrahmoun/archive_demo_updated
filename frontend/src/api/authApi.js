import { api } from "./http";

export async function loginRequest(username, password) {
  const response = await api.post("/api/auth/login/", { username, password });
  return response.data;
}

export async function meRequest() {
  const response = await api.get("/api/auth/me/");
  return response.data;
}

export async function logoutRequest(refresh) {
  const response = await api.post("/api/auth/logout/", { refresh });
  return response.data;
}
