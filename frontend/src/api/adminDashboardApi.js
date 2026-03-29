import { api } from "./http";

export async function getAdminDashboard() {
  const response = await api.get("/api/admin/dashboard/");
  return response.data;
}
