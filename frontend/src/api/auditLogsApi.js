import { api } from "./http";

export async function getAuditLogs(params) {
  const response = await api.get("/api/audit-logs/", { params });
  return response.data;
}

export async function getAuditLogById(id) {
  const response = await api.get(`/api/audit-logs/${id}/`);
  return response.data;
}
