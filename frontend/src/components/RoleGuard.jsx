import { ForbiddenPage } from "../pages/ForbiddenPage";
import { useAuth } from "../auth/useAuth";
import { LoadingBlock } from "./StateBlock";

export function RoleGuard({ allowedRoles, children }) {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return <LoadingBlock />;
  }

  if (!user || !allowedRoles.includes(user.role)) {
    return <ForbiddenPage />;
  }

  return children;
}
