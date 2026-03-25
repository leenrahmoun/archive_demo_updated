"""Dossier workflows enforced at service/API layer."""

from typing import Any

from django.db import transaction

from core.models import Dossier, Document, User


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

    dossier = Dossier(created_by=actor, **dossier_data)
    dossier.full_clean()
    dossier.save()

    document = Document(
        dossier=dossier,
        created_by=actor,
        **first_document_data,
    )
    document.full_clean()
    document.save()
    return dossier, document

