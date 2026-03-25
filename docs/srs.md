# SRS - Archive Management System (MVP)

## Product Goal

Build an internal archive system to manage employee dossiers and linked administrative documents with strict role-based workflow and auditable state transitions.

## Functional Requirements

- FR-01: Create dossier with first document in one transaction.
- FR-01a: Empty dossier creation is forbidden.
- FR-01b: This rule is enforced at service/API layer (not model-only checks).
- FR-01c: If first document creation fails, dossier creation must be rolled back atomically.
- FR-02: Store employee identity/location fields in dossier only.
- FR-03: Add document to existing dossier.
- FR-04: Edit documents only in `draft` and `rejected` (role-dependent).
- FR-05: Submit document for review (`pending`) after validations.
- FR-06: Auditor/Admin can approve or reject with mandatory reason on reject.
- FR-07: Soft-delete and restore workflow as per role policy.
- FR-08: Global search across dossier and document fields.
- FR-09: Rejected-documents worklist for correction and resubmission.
- FR-10: Read-only experience for `reader` limited to approved docs.
- FR-11: Full audit log for business actions.
- FR-12: Lookup endpoints for document types and governorates.

## Non-Functional Requirements

- NFR-01: PostgreSQL indexing strategy for fast search and queue retrieval.
- NFR-02: Data integrity via FK + unique + partial unique constraints.
- NFR-03: File validation at UI, API, and DB levels.
- NFR-04: No auto-save; explicit save actions only.
- NFR-05: Secure file access through backend authorization checks.
- NFR-06: Arabic-ready UI and RTL support.
- NFR-07: Operational auditability and traceability of changes.

## Roles & Permissions (MVP)

- `admin`
  - Manage users, lookups, all review actions.
  - Exceptional modification capability.
  - View full audit log.
- `data_entry`
  - Create dossier + first doc, add/edit draft/rejected docs.
  - Submit/resubmit for review.
  - Soft delete only draft docs.
- `auditor`
  - Review pending docs only.
  - Approve/reject only.
- `reader`
  - Search dossiers and view/download approved docs only.

## Modules

- M-01 Auth & Session (JWT).
- M-02 Dossiers.
- M-03 Documents & Upload.
- M-04 Review Queue.
- M-05 Rejected Documents Workspace.
- M-06 Global Search.
- M-07 Lookup Management.
- M-08 User Management.
- M-09 Audit Log.

## Technical Constraints

- Frontend: React 18 + Vite + Router + Query + RHF + Tailwind + Zustand.
- Backend: Django + DRF + SimpleJWT.
- Database: PostgreSQL 15+.
- File types: `application/pdf` only.
- File size: min 100KB, max 15MB.
- Storage path: `/archive/{L1}/{L2}/{dossier_id}/{doc_type}_{doc_id}.ext`.

## Acceptance Criteria (MVP Gate)

- AC-01: No dossier can be created without first document.
- AC-01a: Dossier creation endpoint rejects requests without first document payload.
- AC-01b: Transaction rollback is verified when first document create fails.
- AC-02: Document submit blocked unless all required fields + valid file exist.
- AC-03: Role restrictions enforced server-side for all endpoints.
- AC-04: `rejection_reason` required on reject transition.
- AC-05: Search returns correct filtered results by role visibility.
- AC-06: Soft-deleted documents excluded by default queries.
- AC-07: Audit log rows created for create/update/submit/approve/reject/delete/restore.

