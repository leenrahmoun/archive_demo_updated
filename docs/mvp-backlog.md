# MVP Backlog

## Phase 1 - Foundation

- [x] Initialize backend Django project and `core` app.
- [x] Configure PostgreSQL, DRF, SimpleJWT, CORS, env-based settings.
- [x] Create custom `User` model with role enum and active flag.
- [ ] Add migrations pipeline and seed commands framework.

## Phase 2 - Data Model

- [x] Implement models: `Governorate`, `DocumentType`, `Dossier`, `Document`, `AuditLog`.
- [x] Add DB constraints and indexes (including partial unique on active docs).
- [x] Add model-level validation for PDF file type, file size, and state transitions.
- [x] Add admin registration for key entities.

## Phase 2.5 - Service/API Rule Enforcement

- [x] Add service function to create dossier + first document atomically.
- [x] Enforce "no empty dossier" in service/API layer (request must include first document).
- [x] Wrap flow in `transaction.atomic()` and rollback dossier on document creation failure.

## Phase 3 - API

- [ ] Auth endpoints (`login`, `refresh`, `logout`, `me`).
- [ ] Dossier list/detail/create/update endpoints with search and pagination.
- [ ] Document CRUD endpoints with role-aware filtering.
- [ ] Workflow endpoints: `submit`, `approve`, `reject`, `restore`.
- [ ] Lookup endpoints for document types/governorates.
- [ ] Audit queue endpoint for pending-first review flow.

## Phase 4 - Frontend Skeleton

- [ ] Bootstrap React app with routing and role-based route guards.
- [ ] Auth state and token refresh flow.
- [ ] Dossier list/search page.
- [ ] Dossier detail + documents tab.
- [ ] Add/edit document form with file uploader constraints.
- [ ] Rejected documents page for correction loop.
- [ ] Auditor queue and decision page.

## Phase 5 - Quality

- [ ] Unit tests for model constraints and transitions.
- [ ] API permission tests per role and document state.
- [ ] Integration tests for file-upload save consistency.
- [ ] Seed fixtures for 59 document types and governorates.

## Definition of Done (MVP)

- [ ] Core workflows pass automated tests.
- [ ] Role policies validated end-to-end.
- [ ] No critical lint/test failures.
- [ ] Ready for deployment on Nginx + Gunicorn + PostgreSQL.

