import axios from "axios";
import { getAccessToken, getRefreshToken, setTokens, clearTokens } from "../auth/tokenStorage";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export const api = axios.create({
  baseURL: BASE_URL,
});

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (!originalRequest || originalRequest._retry) {
      return Promise.reject(error);
    }

    if (error.response?.status !== 401) {
      return Promise.reject(error);
    }

    const refresh = getRefreshToken();
    if (!refresh) {
      window.dispatchEvent(new Event("auth:session-expired"));
      clearTokens();
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    try {
      const refreshResponse = await axios.post(`${BASE_URL}/api/auth/refresh/`, { refresh });
      setTokens({
        access: refreshResponse.data.access,
        refresh: refreshResponse.data.refresh || refresh,
      });
      originalRequest.headers.Authorization = `Bearer ${refreshResponse.data.access}`;
      return api(originalRequest);
    } catch (refreshError) {
      window.dispatchEvent(new Event("auth:session-expired"));
      clearTokens();
      return Promise.reject(refreshError);
    }
  }
);
