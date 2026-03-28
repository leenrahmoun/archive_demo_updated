from math import ceil
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction

from core.models import AuditAction, Document, DocumentStatus, UserRole
from core.services.audit_log_service import create_audit_log


class DocumentUploadError(ValueError):
    """Raised when an uploaded document file violates current PDF rules."""


class DocumentFileReplacementError(ValueError):
    """Raised when a document PDF replacement violates current business rules."""


def validate_uploaded_pdf(uploaded_file) -> dict[str, int | str]:
    if uploaded_file is None:
        raise DocumentUploadError("PDF file is required.")

    original_name = getattr(uploaded_file, "name", "") or ""
    if not original_name.lower().endswith(".pdf"):
        raise DocumentUploadError("Only PDF uploads are allowed.")

    mime_type = getattr(uploaded_file, "content_type", "") or Document.PDF_MIME_TYPE
    if mime_type != Document.PDF_MIME_TYPE:
        raise DocumentUploadError("Only PDF uploads are allowed.")

    file_size_kb = ceil(uploaded_file.size / 1024)
    if file_size_kb < Document.MIN_FILE_SIZE_KB or file_size_kb > Document.MAX_FILE_SIZE_KB:
        raise DocumentUploadError(
            f"File size must be between {Document.MIN_FILE_SIZE_KB}KB and {Document.MAX_FILE_SIZE_KB}KB."
        )

    return {
        "file_size_kb": file_size_kb,
        "mime_type": mime_type,
    }


def build_document_upload_path(*, dossier_id: int, uploaded_file) -> str:
    suffix = Path(getattr(uploaded_file, "name", "") or "").suffix.lower()
    if suffix != ".pdf":
        suffix = ".pdf"

    relative_path = Path(settings.DOCUMENT_UPLOAD_SUBDIR) / f"dossier_{dossier_id}" / f"{uuid4().hex}{suffix}"
    return relative_path.as_posix()


def store_uploaded_pdf(*, dossier_id: int, uploaded_file) -> dict[str, int | str]:
    derived_values = validate_uploaded_pdf(uploaded_file)
    stored_path = default_storage.save(
        build_document_upload_path(dossier_id=dossier_id, uploaded_file=uploaded_file),
        uploaded_file,
    )
    return {
        "file_path": Path(stored_path).as_posix(),
        **derived_values,
    }


def delete_uploaded_pdf(file_path: str | None) -> None:
    if file_path and default_storage.exists(file_path):
        default_storage.delete(file_path)


@transaction.atomic
def replace_document_pdf(*, actor, document, uploaded_file):
    if actor.role != UserRole.DATA_ENTRY:
        raise DocumentFileReplacementError("You do not have permission to replace document files.")
    if document.created_by_id != actor.id:
        raise DocumentFileReplacementError("You can only replace files for your own documents.")
    if document.is_deleted:
        raise DocumentFileReplacementError("Soft-deleted documents cannot be modified.")
    if document.status not in {DocumentStatus.DRAFT, DocumentStatus.REJECTED}:
        raise DocumentFileReplacementError("Document file can only be replaced when status is draft or rejected.")

    old_file_path = document.file_path
    old_values = {
        "file_path": document.file_path,
        "file_size_kb": document.file_size_kb,
        "mime_type": document.mime_type,
        "status": document.status,
    }
    stored_file_path = None

    try:
        stored_file_data = store_uploaded_pdf(dossier_id=document.dossier_id, uploaded_file=uploaded_file)
        stored_file_path = stored_file_data["file_path"]
        document.file_path = stored_file_data["file_path"]
        document.file_size_kb = stored_file_data["file_size_kb"]
        document.mime_type = stored_file_data["mime_type"]
        document.full_clean()
        document.save(update_fields=["file_path", "file_size_kb", "mime_type", "updated_at"])
        create_audit_log(
            user=actor,
            action=AuditAction.REPLACE_FILE,
            entity_type="document",
            entity_id=document.id,
            old_values=old_values,
            new_values={
                "file_path": document.file_path,
                "file_size_kb": document.file_size_kb,
                "mime_type": document.mime_type,
                "status": document.status,
            },
        )
        delete_uploaded_pdf(old_file_path)
        return document
    except Exception:
        delete_uploaded_pdf(stored_file_path)
        raise
