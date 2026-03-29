import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import ministryLogo from "../assets/logo/ministry-logo.svg";

const CREATE_ROLES = new Set(["admin", "data_entry"]);
const AUDIT_ROLES = new Set(["admin"]);
const ADMIN_ROLES = new Set(["admin"]);
const REVIEW_QUEUE_ROLES = new Set(["auditor", "admin"]);

const ROLE_LABELS = {
  admin: "مدير النظام",
  auditor: "مدقق",
  data_entry: "مدخل بيانات",
  reader: "قارئ",
};

export function AppLayout() {
  const { user, logout } = useAuth();
  const canCreate = CREATE_ROLES.has(user?.role);
  const canViewAudit = AUDIT_ROLES.has(user?.role);
  const canViewAdminDashboard = ADMIN_ROLES.has(user?.role);
  const canManageUsers = ADMIN_ROLES.has(user?.role);
  const canManageDocumentTypes = ADMIN_ROLES.has(user?.role);
  const canViewReviewQueue = REVIEW_QUEUE_ROLES.has(user?.role);
  const roleLabel = ROLE_LABELS[user?.role] || user?.role || "مستخدم";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar__heading">
          <span className="sidebar__eyebrow">منصة وزارية داخلية</span>
          <h1>نظام الأرشفة والوثائق</h1>
          <p>إدارة مؤسسية للأضابير والوثائق وسير المراجعة بواجهة عربية رسمية وواضحة.</p>
        </div>

        <nav className="sidebar__nav">
          {canViewAdminDashboard ? <NavLink to="/admin/dashboard">لوحة الإدارة</NavLink> : null}
          <NavLink to="/dossiers">الأضابير</NavLink>
          <NavLink to="/documents">الوثائق</NavLink>
          {canViewReviewQueue ? <NavLink to="/review-queue">قائمة المراجعة</NavLink> : null}
          {canViewAudit ? <NavLink to="/audit-logs">سجل التدقيق</NavLink> : null}
          {canManageUsers ? <NavLink to="/admin/users">إدارة المستخدمين</NavLink> : null}
          {canManageDocumentTypes ? <NavLink to="/admin/document-types">إدارة أنواع الوثائق</NavLink> : null}
          {canCreate ? <NavLink to="/dossiers/new">إنشاء أضبارة</NavLink> : null}
        </nav>

        <div className="sidebar__footer">
          <span className="sidebar__role-pill">{roleLabel}</span>
          <strong>{user?.username}</strong>
          <p>الوصول الحالي إلى الواجهة المؤسسية الداخلية.</p>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="topbar__identity" aria-label="الهوية المؤسسية للنظام">
            <div className="topbar__logo-shell">
              <img src={ministryLogo} alt="شعار وزارة التطوير الإداري" className="topbar__logo" />
            </div>
            <div className="topbar__identity-copy">
              <strong>منصة الأرشفة المؤسسية</strong>
              <span>إدارة الوثائق والأضابير ومسارات المراجعة اليومية</span>
            </div>
          </div>

          <div className="topbar__meta">
            <div className="topbar__user-card">
              <strong>{user?.username}</strong>
              <span>{roleLabel}</span>
            </div>

            <div className="topbar-actions">
              {canViewAdminDashboard ? (
                <Link to="/admin/dashboard" className="topbar__link topbar__link--accent">
                  لوحة الإدارة
                </Link>
              ) : null}
              <Link to="/dossiers" className="topbar__link">
                الأضابير
              </Link>
              <Link to="/documents" className="topbar__link">
                الوثائق
              </Link>
              {canViewReviewQueue ? (
                <Link to="/review-queue" className="topbar__link">
                  قائمة المراجعة
                </Link>
              ) : null}
              <button type="button" className="btn-danger topbar__logout" onClick={logout}>
                تسجيل الخروج
              </button>
            </div>
          </div>
        </header>

        <Outlet />
      </main>
    </div>
  );
}
