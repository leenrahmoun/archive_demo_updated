import { api } from "./http";

export async function getDocuments(params) {
  const response = await api.get("/api/documents/", { params });
  return response.data;
}

export async function getDocumentById(id) {
  const response = await api.get(`/api/documents/${id}/`);
  return response.data;
}

export async function getDocumentPdfBlob(id) {
  const response = await api.get(`/api/documents/${id}/file/`, {
    responseType: "blob",
  });
  return response.data;
}

export async function replaceDocumentPdf(id, file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await api.post(`/api/documents/${id}/replace-file/`, formData);
  return response.data;
}

export async function submitDocument(id) {
  const response = await api.post(`/api/documents/${id}/submit/`, {});
  return response.data;
}

export async function approveDocument(id) {
  const response = await api.post(`/api/documents/${id}/approve/`, {});
  return response.data;
}

export async function rejectDocument(id, rejection_reason) {
  const response = await api.post(`/api/documents/${id}/reject/`, { rejection_reason });
  return response.data;
}

export async function softDeleteDocument(id) {
  const response = await api.post(`/api/documents/${id}/soft-delete/`, {});
  return response.data;
}

export async function createDocument(payload) {
  const response = await api.post("/api/documents/", payload);
  return response.data;
}

export async function updateDocument(id, payload) {
  const response = await api.put(`/api/documents/${id}/`, payload);
  return response.data;
}

export async function getAuditorReviewQueue(params) {
  const response = await api.get("/api/auditor/review-queue/", { params });
  return response.data;
}
