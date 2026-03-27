# Implementation Backlog / Deferred Items

## Deferred Item 15: Soft Delete/Restore for Documents

**Status:** Deferred (not part of current approved core requirements)

**Description:**
Allow restoring soft-deleted documents with clear permission rules, audit logging, and UI restore action.

**Requirements:**
- Backend restore endpoint (`POST /api/documents/{id}/restore/`)
- Permission rules: Admin can restore any document, Data Entry can only restore their own
- Audit logging for restore actions
- Frontend UI restore button in document list
- Show deleted status indicator in UI

**Files That Were Modified (now reverted):**
- `backend/core/services/document_workflow_service.py` - Added `restore_document()` function
- `backend/core/permissions.py` - Added `restore` action to `DocumentWorkflowPermission`
- `backend/core/views.py` - Added `DocumentRestoreAPIView` class
- `backend/core/urls.py` - Added restore endpoint URL pattern
- `frontend/src/api/documentsApi.js` - Added `restoreDocument()` API function
- `frontend/src/pages/DocumentsListPage.jsx` - Added delete/restore buttons
- `backend/core/tests.py` - Added `DocumentSoftDeleteRestoreTests` class

**Note:** This work was started but reverted to stay aligned with the approved plan.

## Deferred Item 16: Auditor Review Queue Page

**Status:** Deferred (not part of current approved core requirements)

**Description:**
A dedicated operational page for auditors showing only pending documents waiting for their review decision.

**Requirements:**
- Dedicated page for auditor role only
- Shows only pending documents waiting for the auditor's decision
- Limited to documents from data_entry users assigned to that auditor
- Must clearly show the username/name of the user who submitted the document
- Must include direct approve/reject actions
- Different from the general documents list - focused operational queue

**Note:** This is different from the general documents list because it is a focused operational queue for daily review tasks.
