import { api } from "./http";

export async function getDossiers(params) {
  const response = await api.get("/api/dossiers/", { params });
  return response.data;
}

export async function getDossierById(id) {
  const response = await api.get(`/api/dossiers/${id}/`);
  return response.data;
}

export async function createDossier(payload) {
  const response = await api.post("/api/dossiers/", payload);
  return response.data;
}
