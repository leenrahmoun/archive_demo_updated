import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { LoadingBlock } from "./StateBlock";

export function ProtectedRoute({ children }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <LoadingBlock />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location, reason: "unauthorized" }} replace />;
  }

  return children;
}
