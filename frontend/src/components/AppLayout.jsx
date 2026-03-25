import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/useAuth";

const CREATE_ROLES = new Set(["admin", "data_entry"]);
const AUDIT_ROLES = new Set(["admin"]);

export function AppLayout() {
  const { user, logout } = useAuth();
  const canCreate = CREATE_ROLES.has(user?.role);
  const canViewAudit = AUDIT_ROLES.has(user?.role);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1>أرشفة الوثائق</h1>
        <nav>
          <NavLink to="/dossiers">الأضابير</NavLink>
          <NavLink to="/documents">الوثائق</NavLink>
          {canViewAudit ? <NavLink to="/audit-logs">سجل التدقيق</NavLink> : null}
          {canCreate ? <NavLink to="/dossiers/new">إنشاء إضبارة</NavLink> : null}
        </nav>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <strong>{user?.username}</strong>
            <span className="muted"> - {user?.role}</span>
          </div>
          <div className="topbar-actions">
            <Link to="/dossiers">الرئيسية</Link>
            <Link to="/documents">الوثائق</Link>
            {canViewAudit ? <Link to="/audit-logs">سجل التدقيق</Link> : null}
            {canCreate ? <Link to="/dossiers/new">إنشاء إضبارة</Link> : null}
            <button type="button" className="btn-danger" onClick={logout}>
              تسجيل الخروج
            </button>
          </div>
        </header>
        <Outlet />
      </main>
    </div>
  );
}
