from math import ceil
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.files.storage import default_storage

from core.models import Document


class DocumentUploadError(ValueError):
    """Raised when an uploaded document file violates current PDF rules."""


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
