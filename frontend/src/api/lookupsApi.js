import { api } from "./http";

export async function getGovernorates() {
  const response = await api.get("/api/governorates/");
  return response.data;
}

export async function getDocumentTypes() {
  const response = await api.get("/api/document-types/");
  return response.data;
}
