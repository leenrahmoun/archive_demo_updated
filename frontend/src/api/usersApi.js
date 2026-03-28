import { api } from "./http";

export async function getUsers(params = {}) {
  const response = await api.get("/api/users/", { params });
  return response.data;
}

export async function getUserById(id) {
  const response = await api.get(`/api/users/${id}/`);
  return response.data;
}

export async function createUser(data) {
  const response = await api.post("/api/users/", data);
  return response.data;
}

export async function updateUser(id, data) {
  const response = await api.put(`/api/users/${id}/`, data);
  return response.data;
}

export async function deleteUser(id) {
  const response = await api.delete(`/api/users/${id}/`);
  return response.data;
}
