from core.models import Document, DocumentStatus, Dossier, UserRole


AUDITOR_VISIBLE_DOCUMENT_STATUSES = (
    DocumentStatus.PENDING,
    DocumentStatus.REJECTED,
    DocumentStatus.APPROVED,
)


def get_document_queryset_for_user(user, *, deleted_state=False):
    if not user or not user.is_authenticated:
        return Document.objects.none()

    queryset = Document.objects.all()
    if deleted_state is not None:
        queryset = queryset.filter(is_deleted=deleted_state)

    if user.role == UserRole.ADMIN:
        return queryset
    if user.role == UserRole.DATA_ENTRY:
        return queryset.filter(created_by=user)
    if user.role == UserRole.AUDITOR:
        return queryset.filter(
            created_by__assigned_auditor=user,
            status__in=AUDITOR_VISIBLE_DOCUMENT_STATUSES,
        )
    if user.role == UserRole.READER:
        if deleted_state:
            return Document.objects.none()
        return queryset.filter(status=DocumentStatus.APPROVED)
    return Document.objects.none()


def get_document_detail_queryset_for_user(user):
    return get_document_queryset_for_user(user, deleted_state=False)


def get_document_review_scope_queryset_for_user(user):
    if not user or not user.is_authenticated:
        return Document.objects.none()
    if user.role == UserRole.ADMIN:
        return Document.objects.filter(is_deleted=False)
    if user.role == UserRole.AUDITOR:
        return Document.objects.filter(is_deleted=False, created_by__assigned_auditor=user)
    return Document.objects.none()


def get_review_queue_queryset_for_user(user):
    if not user or not user.is_authenticated:
        return Document.objects.none()
    if user.role == UserRole.ADMIN:
        return Document.objects.filter(is_deleted=False, status=DocumentStatus.PENDING)
    if user.role == UserRole.AUDITOR:
        return Document.objects.filter(
            is_deleted=False,
            created_by__assigned_auditor=user,
            status=DocumentStatus.PENDING,
        )
    return Document.objects.none()


def get_dossier_queryset_for_user(user):
    if not user or not user.is_authenticated:
        return Dossier.objects.none()
    queryset = Dossier.objects.all()
    if user.role == UserRole.DATA_ENTRY:
        return queryset.filter(created_by=user)
    if user.role == UserRole.AUDITOR:
        return queryset.filter(created_by__assigned_auditor=user)
    return queryset


def get_dossier_documents_for_user(user, dossier):
    queryset = dossier.documents.filter(is_deleted=False)
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.role == UserRole.ADMIN:
        return queryset
    if user.role == UserRole.DATA_ENTRY:
        return queryset.filter(created_by=user)
    if user.role == UserRole.AUDITOR:
        return queryset.filter(
            created_by__assigned_auditor=user,
            status__in=AUDITOR_VISIBLE_DOCUMENT_STATUSES,
        )
    if user.role == UserRole.READER:
        return queryset.filter(status=DocumentStatus.APPROVED)
    return queryset.none()
