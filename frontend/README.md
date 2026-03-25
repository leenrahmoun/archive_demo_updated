# Frontend — Document Archiving MVP

React + Vite frontend for the document archiving system.

---

## Setup

```bash
npm install
npm run dev    # http://localhost:5173
```

The frontend expects the Django backend running at `http://127.0.0.1:8000`.
API base URL is configured in `src/api/` (uses the Vite dev proxy or direct URL).

---

## Pages

| Route | Page | Access |
|---|---|---|
| `/login` | Login | Public |
| `/dossiers` | Dossier list with filters | All roles |
| `/dossiers/new` | Create dossier + first document | admin, data_entry |
| `/dossiers/:id` | Dossier detail + documents | All roles |
| `/dossiers/:id/documents/new` | Add document to dossier | admin, data_entry |
| `/documents` | Document list with filters | All roles |
| `/documents/:id` | Document detail + workflow actions | All roles |
| `/documents/:id/edit` | Edit draft/rejected document | admin, data_entry |
| `/audit-logs` | Audit log list with filters | admin only |
| `/audit-logs/:id` | Audit log entry detail | admin only |

---

## Role-based UI

| UI element | Visible to |
|---|---|
| "إنشاء إضبارة" nav link | admin, data_entry |
| "إضافة وثيقة" button (dossier detail) | admin, data_entry |
| "سجل التدقيق" nav link | admin only |
| Submit / "إرسال" button | admin, data_entry (draft or rejected documents) |
| Approve / Reject buttons | admin, auditor (pending documents) |
| Soft-delete button | admin, data_entry |
| Edit link | admin, data_entry |

---

## Key Components

| Component | Purpose |
|---|---|
| `AppLayout` | Shell: sidebar nav + topbar with role-aware links |
| `ProtectedRoute` | Redirects unauthenticated users to /login |
| `RoleGuard` | Renders ForbiddenPage for unauthorized roles |
| `DocumentWorkflowActions` | Submit / approve / reject / soft-delete panel |
| `StatusBadge` | Colour-coded document status chip |
| `PaginationControls` | Prev/next pagination |
| `FilterSection` | Filter bar used across list pages |
