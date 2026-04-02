# Security Hardening Summary

## 1. Overview

The completed hardening track tightened document authorization, JWT session handling, inactive-account enforcement, and security-relevant audit visibility without changing the overall backend/frontend architecture.

Main logic now lives in:
- `backend/core/access.py`
- `backend/core/views.py`
- `backend/core/permissions.py`
- `backend/core/services/document_workflow_service.py`
- `backend/config/settings.py`
- `backend/core/auth.py`
- `backend/core/auth_views.py`
- `backend/core/services/audit_log_service.py`
- `backend/core/serializers.py`
- `frontend/src/api/http.js`

## 2. Backend Access Control Hardening

Document authorization was centralized in `backend/core/access.py` via reusable policy and scope helpers for view, edit, submit, approve, reject, soft delete, and restore decisions.

Object-level enforcement now happens consistently in `backend/core/views.py` and `backend/core/services/document_workflow_service.py`, so knowing a document ID does not bypass authorization.

List/detail/file visibility now uses the same document visibility scope, keeping `GET /api/documents/`, `GET /api/documents/{id}/`, and `GET /api/documents/{id}/file/` aligned.

Reviewer assignment enforcement is explicit and shared across:
- review queue scope in `backend/core/access.py`
- review detail access in `backend/core/views.py`
- approve/reject workflow checks in `backend/core/services/document_workflow_service.py`

## 3. JWT/Auth Hardening

JWT settings in `backend/config/settings.py` now enforce:
- shorter access token lifetime
- refresh token rotation
- blacklist-after-rotation behavior

Active-account enforcement is centralized through:
- `backend/core/auth.py` for protected endpoint authentication
- `backend/core/auth_views.py` for audited login and refresh flows

Current frontend/backend assumption: successful `POST /api/auth/refresh/` responses return both `access` and `refresh`, and the client must replace the stored refresh token immediately.

## 4. Audit Logging Expansion

Security-related audit logging was expanded using the existing audit model and helpers in:
- `backend/core/services/audit_log_service.py`
- `backend/core/auth_views.py`
- `backend/core/views.py`
- `backend/core/permissions.py`
- `backend/core/serializers.py`

Newly logged security-relevant events now include:
- login success
- failed login for an existing user
- logout
- refresh failure for resolvable users
- denied sensitive document workflow attempts
- role changes
- reviewer assignment / reassignment changes

Current audit-model limitation: `AuditLog.user` requires a concrete user foreign key, so the system still cannot cleanly log unknown-username login failures or fully unattributable events without redesigning the audit model.

## 5. Frontend Follow-Up That Was Implemented

The refresh interceptor in `frontend/src/api/http.js` now stores the newest rotated refresh token returned by `POST /api/auth/refresh/` instead of re-saving the stale token.

Logout already reads the currently stored refresh token at call time through `frontend/src/auth/AuthContext.jsx` and `frontend/src/auth/tokenStorage.js`, so it now uses the latest rotated refresh token automatically.

## 6. Current Known Limitations / Future Follow-Up

- Dossier hardening has not been done yet; the centralized access/policy work currently covers documents only.
- The audit model still cannot cleanly represent unknown-username or otherwise unattributable security events without a schema/design change.
- Manual frontend smoke tests are still important because there is no automated frontend test coverage for token rotation, storage replacement, and logout payload validation.
