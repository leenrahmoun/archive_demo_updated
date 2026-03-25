# Document Archiving MVP

A role-based internal document archiving system for employee dossiers and administrative documents, built with Django REST Framework and React.

| Layer | Technology |
|---|---|
| Backend | Python 3, Django, Django REST Framework |
| Auth | SimpleJWT (access + refresh) |
| Database | PostgreSQL |
| Frontend | React 18, Vite, React Router |
| Styling | CSS — RTL/Arabic-ready |

---

## Table of Contents

- [Current MVP Status](#current-mvp-status)
- [Product Goal](#product-goal)
- [MVP Scope](#mvp-scope)
- [Roles and Permissions](#roles-and-permissions)
- [Core Business Rules](#core-business-rules)
- [Document Workflow](#document-workflow)
- [File Policy](#file-policy)
- [Project Structure](#project-structure)
- [Environment Variables](#environment-variables)
- [Backend Setup](#backend-setup)
- [Frontend Setup](#frontend-setup)
- [Seed Data](#seed-data)
- [Role Preparation](#role-preparation)
- [API Reference](#api-reference)
- [Testing](#testing)
- [Manual Verification](#manual-verification)
- [Demo Walkthrough](#demo-walkthrough)
- [Future Improvements](#future-improvements)

---

## Current MVP Status

> **Status: Working CRUD + Workflow MVP — verified manually across all user roles.**

The core dossier/document lifecycle, role-based access control, approval workflow, and audit logging are fully implemented and tested. This build is suitable for MVP demo, internal review, and next-phase scoping.

---

## Product Goal

An internal archive system that manages employee dossiers and the administrative documents attached to them, with strict role-based workflow, auditable business actions, and safe visibility rules enforced per role.

- A **dossier** stores employee identity and physical archive location
- A **document** stores the administrative event linked to that dossier
- A dossier **cannot be created without a first document** — creation is atomic
- Document lifecycle follows controlled, auditable state transitions

---

## MVP Scope

### Implemented

- **JWT authentication** — login, refresh, logout, current user (`/me`)
- **Dossier management** — create with first document, list, search/filter/order, detail view
- **Document management** — create for existing dossier, list, search/filter/order, detail, edit draft/rejected
- **Document workflow** — submit, approve, reject, soft-delete, correct rejected and resubmit
- **Lookup APIs** — governorates, document types
- **Audit logs** — full log available to `admin` only
- **Seed command** — 14 Syrian governorates + 59 document types from the design study
- **Role-based UI** and route protection

### Out of Scope for This MVP

- Advanced dashboard and analytics
- Full user management UI
- Deployment automation
- Production storage and security hardening
- Advanced auditor queue UX

---

## Roles and Permissions

### `admin`
- Full access across all features
- Create and manage dossiers and documents
- Perform all document workflow actions: submit, approve, reject, soft-delete
- Access full audit logs

### `data_entry`
- Create dossiers with a first document
- Add documents to existing dossiers
- Edit `draft` and `rejected` documents
- Submit and resubmit documents for review
- Soft-delete `draft` documents only

### `auditor`
- Approve or reject `pending` documents
- View reviewable documents only
- **Cannot** create dossiers or documents
- **Cannot** access audit logs

### `reader`
- Read-only access — sees **approved documents only**
- Draft, pending, and rejected documents are not visible
- No workflow actions
- No audit log access

---

## Core Business Rules

- A dossier **must be created together with its first document** — empty dossier creation is forbidden
- Dossier + first document creation is a single atomic operation
- Document workflow actions (submit, approve, reject) apply to **documents only**, not dossiers
- File validation is enforced on both backend and frontend
- **Soft delete only** — no physical deletion in this MVP
- Reader visibility is strictly limited to approved content
- Audit logs are restricted to `admin` only

---

## Document Workflow

### Status values

| Status | Description |
|---|---|
| `draft` | Created, not yet submitted |
| `pending` | Submitted and awaiting review |
| `approved` | Approved by auditor or admin |
| `rejected` | Rejected with a mandatory reason |

### Transitions

```
data_entry / admin:
    draft ──────────────────────► pending

auditor / admin:
    pending ─────────────────────► approved
    pending ─────────────────────► rejected  (reason required)

data_entry / admin:
    rejected ──► edit ──► resubmit ──► pending
```

### Rules

- Rejection **requires** a `rejection_reason` field
- A rejected document can be corrected and resubmitted, returning it to `pending`
- Invalid transitions (e.g. approving a `draft`) return `400 Bad Request`

---

## File Policy

| Rule | Value |
|---|---|
| Accepted format | PDF only |
| Minimum size | 100 KB |
| Maximum size | 15 MB |

Both backend and frontend enforce these constraints.

---

## Project Structure

```
archive-demo/
├── backend/
│   ├── config/                  # Django settings and URL config
│   ├── core/
│   │   ├── management/
│   │   │   └── commands/
│   │   │       ├── seed_lookups.py
│   │   │       └── data/        # Governorate and document type fixtures
│   │   ├── migrations/
│   │   ├── services/            # Business logic layer
│   │   ├── models.py            # User, Dossier, Document, AuditLog
│   │   ├── views.py
│   │   ├── serializers.py
│   │   ├── permissions.py       # Custom DRF permission classes per role
│   │   └── tests.py
│   ├── .env.example
│   ├── requirements.txt
│   └── manage.py
│
├── frontend/
│   ├── src/
│   │   ├── api/                 # Axios client + per-resource modules
│   │   ├── auth/                # Auth context and token handling
│   │   ├── components/          # Shared UI components
│   │   ├── pages/               # Route-level page components
│   │   ├── utils/
│   │   ├── App.jsx
│   │   └── main.jsx
│   └── package.json
│
├── design-study.md
├── docs/
│   ├── srs.md
│   └── mvp-backlog.md
└── README.md
```

---

## Environment Variables

### `backend/.env`

```env
DEBUG=1
SECRET_KEY=your-secret-key

ALLOWED_HOSTS=*
CORS_ALLOW_ALL_ORIGINS=1

# PostgreSQL (primary — intended for all environments)
USE_SQLITE_FALLBACK=0
POSTGRES_DB=archive_demo
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

> Set `USE_SQLITE_FALLBACK=1` only for local development convenience.
> PostgreSQL is the intended database for all other environments.

---

## Backend Setup

### Prerequisites

- Python 3.11+
- PostgreSQL installed and running

### Steps

```bash
# 1. Navigate into the backend directory
cd archive-demo/backend

# 2. Create a virtual environment
python -m venv venv

# 3. Activate the virtual environment
source venv/bin/activate          # Linux / macOS
venv\Scripts\activate             # Windows

# 4. Install dependencies
pip install -r requirements.txt

# 5. Configure environment variables
cp .env.example .env
# Edit .env with your database credentials and secret key

# 6. Apply migrations
python manage.py migrate

# 7. Seed lookup data (governorates + document types)
python manage.py seed_lookups

# 8. Create a superuser
python manage.py createsuperuser

# 9. Start the development server
python manage.py runserver
```

Backend runs at `http://127.0.0.1:8000`.

---

## Frontend Setup

### Prerequisites

- Node.js 18+

### Steps

```bash
cd archive-demo/frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`.

Set the API base URL in the frontend environment config if it differs from the default.

---

## Seed Data

The `seed_lookups` management command loads:

- **14 Syrian governorates**
- **59 document types** grouped according to the design study structure

```bash
python manage.py seed_lookups
```

The command is idempotent and can be safely re-run at any time without creating duplicates.

---

## Role Preparation

After running `createsuperuser`:

1. Open Django Admin at `http://127.0.0.1:8000/admin/`
2. Create users as needed
3. Assign the `role` field on each user:
   - `admin`
   - `data_entry`
   - `auditor`
   - `reader`

---

## API Reference

All protected endpoints require:
```
Authorization: Bearer <access_token>
```

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/token/` | Obtain access + refresh tokens |
| `POST` | `/api/auth/token/refresh/` | Rotate access token |
| `POST` | `/api/auth/logout/` | Blacklist refresh token |
| `GET` | `/api/auth/me/` | Current user profile |

### Dossiers

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/dossiers/` | List dossiers (search, filter, order) |
| `POST` | `/api/dossiers/` | Create dossier + first document (atomic) |
| `GET` | `/api/dossiers/{id}/` | Dossier detail |

### Documents

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/documents/` | List documents (search, filter, order) |
| `POST` | `/api/documents/` | Add document to existing dossier |
| `GET` | `/api/documents/{id}/` | Document detail |
| `PUT` | `/api/documents/{id}/` | Full update of draft/rejected document |
| `PATCH` | `/api/documents/{id}/` | Partial update of draft/rejected document |

### Workflow

| Method | Endpoint | Description | Allowed Roles |
|---|---|---|---|
| `POST` | `/api/documents/{id}/submit/` | Submit draft for review | `data_entry`, `admin` |
| `POST` | `/api/documents/{id}/approve/` | Approve pending document | `auditor`, `admin` |
| `POST` | `/api/documents/{id}/reject/` | Reject with mandatory reason | `auditor`, `admin` |
| `POST` | `/api/documents/{id}/soft-delete/` | Soft-delete document | `data_entry` (draft only), `admin` |

### Lookups

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/governorates/` | List all governorates |
| `GET` | `/api/document-types/` | List all document types |

### Audit Logs

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/audit-logs/` | Paginated audit log — admin only |
| `GET` | `/api/audit-logs/{id}/` | Single audit entry — admin only |

---

## Testing

Run the full test suite from the backend directory:

```bash
cd backend
python manage.py test core -v 2
```

Run specific test classes:

```bash
# Document workflow state transitions
python manage.py test core.tests.DocumentWorkflowApiTests -v 2

# Reader visibility — approved-only content policy
python manage.py test core.tests.DossierDetailDocumentVisibilityTests -v 2

# Audit log access control
python manage.py test core.tests.AuditLogApiTests -v 2
```

---

## Manual Verification

### Verified — Current MVP

These flows have been tested and confirmed working:

**Dossier**
- [x] Create dossier with first document — both saved atomically
- [x] Dossier appears in list
- [x] Dossier detail loads with linked documents

**Document**
- [x] Add document to existing dossier
- [x] Open document detail
- [x] Edit draft document successfully
- [x] Edit rejected document successfully

**Workflow transitions**
- [x] Submit `draft` → status becomes `pending`
- [x] Reject `pending` document with reason → status becomes `rejected`
- [x] Edit rejected document and resubmit → status returns to `pending`
- [x] Approve `pending` document → status becomes `approved`

**Role policy**
- [x] `reader` sees only approved documents — draft/pending/rejected hidden
- [x] `auditor` cannot access dossier or document creation routes
- [x] `auditor` cannot access audit logs
- [x] Audit log endpoint returns `403` for all roles except `admin`

---

### Regression Checklist — Future Releases

Re-run before any significant change to permissions, workflow logic, or serializer layer:

**Authentication**
- [ ] Expired access token returns `401`
- [ ] Valid refresh token issues a new access token
- [ ] Blacklisted refresh token cannot be reused after logout

**Dossier integrity**
- [ ] Creating a dossier without a document is rejected
- [ ] Failed document validation rolls back dossier creation

**Workflow guard rails**
- [ ] Approving a `draft` document returns `400`
- [ ] Rejecting without `rejection_reason` returns `400`
- [ ] `data_entry` cannot approve or reject
- [ ] `auditor` cannot submit

**File validation**
- [ ] Upload under 100 KB is rejected
- [ ] Upload over 15 MB is rejected
- [ ] Non-PDF file is rejected

**Visibility isolation**
- [ ] `reader` receives zero results for non-approved documents
- [ ] `auditor` receives `403` on audit log endpoint
- [ ] `data_entry` receives `403` on audit log endpoint

---

## Demo Walkthrough

### Admin

1. Login as `admin`
2. Create a dossier with its first document
3. Open the dossier detail and add a second document
4. Edit a draft document
5. Submit, approve, and reject documents
6. View audit logs

### Data Entry

1. Login as `data_entry`
2. Create a dossier with its first document
3. Add a document to an existing dossier
4. Edit a draft document and submit it for review
5. After rejection: open the rejected document, edit it, click **Resubmit** — document returns to `pending`

### Auditor

1. Login as `auditor`
2. Open the pending documents queue
3. Approve a document
4. Reject a document with a reason
5. Confirm dossier/document creation pages are inaccessible
6. Confirm audit logs are inaccessible

### Reader

1. Login as `reader`
2. Browse dossiers and open documents
3. Confirm only approved documents are visible
4. Confirm all write actions (edit, submit, approve, reject) are unavailable

---

## Future Improvements

- Dedicated auditor queue page with filtering by date and document type
- Better success/error toast notification system
- Richer filtering and search UX
- Production file storage hardening (object storage backend)
- User management UI (create, assign roles, deactivate)
- Dashboard and operational reporting
- Stronger deployment documentation (Docker, CI/CD)

---

## Notes

- PostgreSQL is the intended database for all environments. `USE_SQLITE_FALLBACK=1` is a development convenience only.
- The UI and API are Arabic/RTL-ready.
- Audit logs are restricted to `admin` only — `auditor` and `reader` roles have no access.
- All deletes are soft — no records are physically removed in this MVP.
