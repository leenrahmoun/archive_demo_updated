import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/useAuth";
import { AppLayout } from "./components/AppLayout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { LoginPage } from "./pages/LoginPage";
import { DossierListPage } from "./pages/DossierListPage";
import { DossierDetailPage } from "./pages/DossierDetailPage";
import { CreateDossierPage } from "./pages/CreateDossierPage";
import { DocumentsListPage } from "./pages/DocumentsListPage";
import { DocumentDetailPage } from "./pages/DocumentDetailPage";
import { AuditLogListPage } from "./pages/AuditLogListPage";
import { AuditLogDetailPage } from "./pages/AuditLogDetailPage";
import { DocumentFormPage } from "./pages/DocumentFormPage";
import { RoleGuard } from "./components/RoleGuard";
import { NotFoundPage } from "./pages/NotFoundPage";
import { UserManagementPage } from "./pages/UserManagementPage";
import { ReviewQueuePage } from "./pages/ReviewQueuePage";

function HomeRedirect() {
  const { isAuthenticated } = useAuth();
  return <Navigate to={isAuthenticated ? "/dossiers" : "/login"} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route path="/login" element={<LoginPage />} />

      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/dossiers" element={<DossierListPage />} />
        <Route
          path="/dossiers/new"
          element={
            <RoleGuard allowedRoles={["admin", "data_entry"]}>
              <CreateDossierPage />
            </RoleGuard>
          }
        />
        <Route path="/dossiers/:id" element={<DossierDetailPage />} />
        <Route
          path="/dossiers/:dossierId/documents/new"
          element={
            <RoleGuard allowedRoles={["admin", "data_entry"]}>
              <DocumentFormPage />
            </RoleGuard>
          }
        />
        <Route path="/documents" element={<DocumentsListPage />} />
        <Route path="/documents/:id" element={<DocumentDetailPage />} />
        <Route path="/documents/:id/edit" element={<DocumentFormPage />} />
        <Route
          path="/audit-logs"
          element={
            <RoleGuard allowedRoles={["admin"]}>
              <AuditLogListPage />
            </RoleGuard>
          }
        />
        <Route
          path="/audit-logs/:id"
          element={
            <RoleGuard allowedRoles={["admin"]}>
              <AuditLogDetailPage />
            </RoleGuard>
          }
        />
        <Route
          path="/review-queue"
          element={
            <RoleGuard allowedRoles={["auditor", "admin"]}>
              <ReviewQueuePage />
            </RoleGuard>
          }
        />
        <Route
          path="/admin/users"
          element={
            <RoleGuard allowedRoles={["admin"]}>
              <UserManagementPage />
            </RoleGuard>
          }
        />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
