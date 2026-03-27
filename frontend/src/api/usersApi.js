import { api } from "./http";

export const getUsers = (params = {}) => {
  return api.get("/api/users/", { params });
};

export const getUserById = (id) => {
  return api.get(`/api/users/${id}/`);
};

export const createUser = (data) => {
  return api.post("/api/users/", data);
};

export const updateUser = (id, data) => {
  return api.put(`/api/users/${id}/`, data);
};

export const deleteUser = (id) => {
  return api.delete(`/api/users/${id}/`);
};
