"""Document workflow actions for MVP."""

from django.db import transaction
from django.utils import timezone

from core.models import AuditAction, AuditLog, Document, DocumentStatus, User, UserRole


class WorkflowError(ValueError):
    """Raised when workflow transition or permission is invalid."""


def _audit(user: User, action: str, document: Document, old_values: dict, new_values: dict) -> None:
    AuditLog.objects.create(
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

