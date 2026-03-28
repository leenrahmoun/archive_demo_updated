import { api } from "./http";

export async function getManagedDocumentTypes(params = {}) {
  const response = await api.get("/api/admin/document-types/", { params });
  return response.data;
}

export async function createManagedDocumentType(data) {
  const response = await api.post("/api/admin/document-types/", data);
  return response.data;
}

export async function updateManagedDocumentType(id, data) {
  const response = await api.put(`/api/admin/document-types/${id}/`, data);
  return response.data;
}

export async function setManagedDocumentTypeActiveState(id, isActive) {
  const response = await api.patch(`/api/admin/document-types/${id}/`, { is_active: isActive });
  return response.data;
}

export async function deleteManagedDocumentType(id) {
  const response = await api.delete(`/api/admin/document-types/${id}/`);
  return response.data;
}
