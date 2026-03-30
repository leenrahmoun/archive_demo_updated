"""Document workflow actions for MVP."""

from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone

from core.models import AuditAction, Document, DocumentStatus, User, UserRole
from core.services.audit_log_service import create_audit_log


class WorkflowError(ValueError):
    """Raised when workflow transition or permission is invalid."""


def _validation_error_to_message(exc: DjangoValidationError) -> str:
    if getattr(exc, "message_dict", None):
        messages = []
        for values in exc.message_dict.values():
            messages.extend(str(value) for value in values)
        if messages:
            return messages[0]
    if getattr(exc, "messages", None):
        return str(exc.messages[0])
    return "The requested workflow change is invalid."


def _audit(user: User, action: str, document: Document, old_values: dict, new_values: dict) -> None:
    create_audit_log(
        user=user,
        action=action,
        entity_type="document",
        entity_id=document.id,
        old_values=old_values,
        new_values=new_values,
    )


@transaction.atomic
def submit_document(*, actor: User, document: Document) -> Document:
    if actor.role not in {UserRole.ADMIN, UserRole.DATA_ENTRY}:
        raise WorkflowError("You do not have permission to submit documents.")
    if actor.role == UserRole.DATA_ENTRY and actor.assigned_auditor_id is None:
        raise WorkflowError("Data entry users must be assigned to an auditor before submitting documents.")
    if document.status not in {DocumentStatus.DRAFT, DocumentStatus.REJECTED}:
        raise WorkflowError("Only draft or rejected documents can be submitted.")
    if document.is_deleted:
        raise WorkflowError("Deleted documents cannot be submitted.")

    old_values = {"status": document.status, "submitted_at": document.submitted_at.isoformat() if document.submitted_at else None, "rejection_reason": document.rejection_reason}
    document.status = DocumentStatus.PENDING
    document.submitted_at = timezone.now()
    document.rejection_reason = None
    document.full_clean()
    document.save(update_fields=["status", "submitted_at", "rejection_reason", "updated_at"])
    _audit(
        actor,
        AuditAction.SUBMIT,
        document,
        old_values,
        {"status": document.status, "submitted_at": document.submitted_at.isoformat(), "rejection_reason": document.rejection_reason},
    )
    return document


@transaction.atomic
def approve_document(*, actor: User, document: Document) -> Document:
    if actor.role not in {UserRole.ADMIN, UserRole.AUDITOR}:
        raise WorkflowError("You do not have permission to approve documents.")
    if actor.role == UserRole.AUDITOR and document.created_by.assigned_auditor_id != actor.id:
        raise WorkflowError("You do not have access to review this document.")
    if document.status != DocumentStatus.PENDING:
        raise WorkflowError("Only pending documents can be approved.")
    if document.is_deleted:
        raise WorkflowError("Deleted documents cannot be approved.")

    old_values = {"status": document.status, "reviewed_by": document.reviewed_by_id, "reviewed_at": document.reviewed_at}
    document.status = DocumentStatus.APPROVED
    document.reviewed_by = actor
    document.reviewed_at = timezone.now()
    document.rejection_reason = None
    document.full_clean()
    document.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"])
    _audit(
        actor,
        AuditAction.APPROVE,
        document,
        old_values,
        {
            "status": document.status,
            "reviewed_by": document.reviewed_by_id,
            "reviewed_at": document.reviewed_at.isoformat(),
            "rejection_reason": document.rejection_reason,
        },
    )
    return document


@transaction.atomic
def reject_document(*, actor: User, document: Document, rejection_reason: str) -> Document:
    if actor.role not in {UserRole.ADMIN, UserRole.AUDITOR}:
        raise WorkflowError("You do not have permission to reject documents.")
    if actor.role == UserRole.AUDITOR and document.created_by.assigned_auditor_id != actor.id:
        raise WorkflowError("You do not have access to review this document.")
    if document.status != DocumentStatus.PENDING:
        raise WorkflowError("Only pending documents can be rejected.")
    if document.is_deleted:
        raise WorkflowError("Deleted documents cannot be rejected.")
    if not rejection_reason:
        raise WorkflowError("rejection_reason is required.")

    old_values = {"status": document.status, "reviewed_by": document.reviewed_by_id, "reviewed_at": document.reviewed_at}
    document.status = DocumentStatus.REJECTED
    document.reviewed_by = actor
    document.reviewed_at = timezone.now()
    document.rejection_reason = rejection_reason
    document.full_clean()
    document.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"])
    _audit(
        actor,
        AuditAction.REJECT,
        document,
        old_values,
        {
            "status": document.status,
            "reviewed_by": document.reviewed_by_id,
            "reviewed_at": document.reviewed_at.isoformat(),
            "rejection_reason": document.rejection_reason,
        },
    )
    return document


@transaction.atomic
def soft_delete_document(*, actor: User, document: Document) -> Document:
    if actor.role not in {UserRole.ADMIN, UserRole.DATA_ENTRY}:
        raise WorkflowError("You do not have permission to soft-delete documents.")
    if document.is_deleted:
        raise WorkflowError("Document is already deleted.")
    if actor.role == UserRole.DATA_ENTRY and document.status != DocumentStatus.DRAFT:
        raise WorkflowError("Data entry can soft-delete draft documents only.")

    old_values = {"is_deleted": document.is_deleted, "deleted_by": document.deleted_by_id, "deleted_at": document.deleted_at}
    document.is_deleted = True
    document.deleted_by = actor
    document.deleted_at = timezone.now()
    document.save(update_fields=["is_deleted", "deleted_by", "deleted_at", "updated_at"])
    _audit(
        actor,
        AuditAction.DELETE,
        document,
        old_values,
        {
            "is_deleted": document.is_deleted,
            "deleted_by": document.deleted_by_id,
            "deleted_at": document.deleted_at.isoformat(),
        },
    )
    return document


@transaction.atomic
def restore_document(*, actor: User, document: Document) -> Document:
    if actor.role not in {UserRole.ADMIN, UserRole.DATA_ENTRY}:
        raise WorkflowError("You do not have permission to restore documents.")
    if not document.is_deleted:
        raise WorkflowError("Document is not deleted.")
    if actor.role == UserRole.DATA_ENTRY and document.created_by_id != actor.id:
        raise WorkflowError("You do not have permission to restore this document.")

    old_values = {"is_deleted": document.is_deleted, "deleted_by": document.deleted_by_id, "deleted_at": document.deleted_at}
    document.is_deleted = False
    document.deleted_by = None
    document.deleted_at = None
    try:
        document.full_clean()
    except DjangoValidationError as exc:
        raise WorkflowError(_validation_error_to_message(exc)) from exc
    document.save(update_fields=["is_deleted", "deleted_by", "deleted_at", "updated_at"])
    _audit(
        actor,
        AuditAction.RESTORE,
        document,
        old_values,
        {
            "is_deleted": document.is_deleted,
            "deleted_by": document.deleted_by_id,
            "deleted_at": document.deleted_at,
        },
    )
    return document

