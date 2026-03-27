"""Dossier workflows enforced at service/API layer."""

from typing import Any

from django.db import transaction

from core.models import Dossier, Document, User
from core.services.document_storage_service import delete_uploaded_pdf, store_uploaded_pdf


class DossierCreationError(ValueError):
    """Raised when dossier creation request violates business rules."""


@transaction.atomic
def create_dossier_with_first_document(
    *,
    actor: User,
    dossier_data: dict[str, Any],
    first_document_data: dict[str, Any] | None,
) -> tuple[Dossier, Document]:
    """
    Create dossier and first document in one atomic transaction.

    Business rules enforced here:
    - Empty dossier creation is forbidden.
    - First document is required in request payload.
    - If document creation fails, dossier is rolled back.
    """
    if not first_document_data:
        raise DossierCreationError("First document is required; empty dossier creation is not allowed.")

    uploaded_file = first_document_data.pop("file", None)
    if uploaded_file is None:
        raise DossierCreationError("First document PDF file is required.")

    dossier = Dossier(created_by=actor, **dossier_data)
    dossier.full_clean()
    dossier.save()

    stored_file_path = None
    try:
        stored_file_data = store_uploaded_pdf(dossier_id=dossier.id, uploaded_file=uploaded_file)
        stored_file_path = stored_file_data["file_path"]
        document = Document(
            dossier=dossier,
            created_by=actor,
            **first_document_data,
            **stored_file_data,
        )
        document.full_clean()
        document.save()
        return dossier, document
    except Exception:
        delete_uploaded_pdf(stored_file_path)
        raise

