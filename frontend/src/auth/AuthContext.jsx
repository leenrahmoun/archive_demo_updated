import { createContext, useEffect, useMemo, useState } from "react";
import { loginRequest, logoutRequest, meRequest } from "../api/authApi";
import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "./tokenStorage";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [authMessage, setAuthMessage] = useState("");

  useEffect(() => {
    const access = getAccessToken();
    if (!access) {
      setIsLoading(false);
      return;
    }
    meRequest()
      .then(setUser)
      .catch(() => {
        clearTokens();
        setUser(null);
      })
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    function onSessionExpired() {
      clearTokens();
      setUser(null);
      setAuthMessage("انتهت الجلسة. يرجى تسجيل الدخول مرة أخرى.");
    }
    window.addEventListener("auth:session-expired", onSessionExpired);
    return () => window.removeEventListener("auth:session-expired", onSessionExpired);
  }, []);

  async function login(username, password) {
    const tokens = await loginRequest(username, password);
    setTokens(tokens);
    const me = await meRequest();
    setUser(me);
    setAuthMessage("");
  }

  async function logout() {
    const refresh = getRefreshToken();
    try {
      if (refresh) {
        await logoutRequest(refresh);
      }
    } finally {
      clearTokens();
      setUser(null);
    }
  }

  const value = useMemo(
    () => ({
      user,
      isLoading,
      isAuthenticated: Boolean(user),
      authMessage,
      setAuthMessage,
      login,
      logout,
    }),
    [user, isLoading, authMessage]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export { AuthContext };
