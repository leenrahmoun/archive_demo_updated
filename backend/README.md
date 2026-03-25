# Backend — Document Archiving MVP

Django + DRF backend for the document archiving system.

---

## Setup

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env with your PostgreSQL credentials
```

Key variables:

| Variable | Description |
|---|---|
| `POSTGRES_DB` | Database name (default: `archive_demo`) |
| `POSTGRES_USER` | DB user (default: `postgres`) |
| `POSTGRES_PASSWORD` | DB password |
| `POSTGRES_HOST` | Host (default: `localhost`) |
| `POSTGRES_PORT` | Port (default: `5432`) |
| `USE_SQLITE_FALLBACK` | Set to `1` for SQLite (dev only) |

### 2. Install and initialise

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_lookups
python manage.py createsuperuser   # first time only
python manage.py runserver         # http://127.0.0.1:8000
```

---

## Seed Data (`seed_lookups`)

Populates two lookup tables. Safe to run multiple times — fully idempotent.

| Table | Count | Notes |
|---|---|---|
| `Governorate` | 14 | All Syrian governorates |
| `DocumentType` | 59 | 7 administrative groups |

```bash
python manage.py seed_lookups
```

---

## User Roles

Set in Django Admin (`/admin/`) on the `User` model:

| Role | Permissions |
|---|---|
| `admin` | Full access, audit logs |
| `data_entry` | Create/edit/submit/soft-delete drafts |
| `auditor` | Read pending+approved documents, approve/reject |
| `reader` | Read approved documents only |

---

## API Overview

All endpoints require JWT auth header: `Authorization: Bearer <access_token>`

| Endpoint | Method | Notes |
|---|---|---|
| `/api/auth/token/` | POST | Obtain tokens |
| `/api/auth/token/refresh/` | POST | Refresh access token |
| `/api/auth/logout/` | POST | Blacklist refresh token |
| `/api/auth/me/` | GET | Current user profile |
| `/api/dossiers/` | GET, POST | List / create dossier with first document |
| `/api/dossiers/{id}/` | GET | Dossier detail (role-filtered documents) |
| `/api/documents/` | GET, POST | List / create documents |
| `/api/documents/{id}/` | GET, PUT, PATCH | Detail / edit draft |
| `/api/documents/{id}/submit/` | POST | draft or rejected → pending |
| `/api/documents/{id}/approve/` | POST | pending → approved |
| `/api/documents/{id}/reject/` | POST | pending → rejected |
| `/api/documents/{id}/soft-delete/` | POST | Soft delete |
| `/api/audit-logs/` | GET | Admin only |
| `/api/audit-logs/{id}/` | GET | Admin only |
| `/api/governorates/` | GET | Lookup |
| `/api/document-types/` | GET | Lookup |

---

## Document Workflow Transitions

```
draft ──[submit]──► pending ──[approve]──► approved
                      │
                   [reject]
                      │
                   rejected ──[edit + resubmit]──► pending
```

---

## Running Tests

```bash
# All tests
python manage.py test core

# Single class
python manage.py test core.tests.DocumentWorkflowApiTests

# Single test
python manage.py test core.tests.DocumentWorkflowApiTests.test_resubmit_rejected_document_returns_to_pending
```

### Test classes

| Class | What it covers |
|---|---|
| `DossierApiTests` | Dossier creation, first-document atomicity |
| `AuthAndLookupApiTests` | Login, logout, governorates, document types |
| `DocumentWorkflowApiTests` | Submit, approve, reject, soft-delete, resubmission |
| `AuditLogApiTests` | Audit log list/filter/detail, role access |
| `DossierListQueryApiTests` | Dossier list filters, search, ordering, pagination |
| `DocumentListQueryApiTests` | Document list filters, role visibility |
| `DocumentCreateUpdateApiTests` | Document create/edit validations |
| `SeedLookupsCommandTests` | seed_lookups idempotency and API visibility |
| `DossierDetailDocumentVisibilityTests` | Per-role nested document filtering in dossier detail |
