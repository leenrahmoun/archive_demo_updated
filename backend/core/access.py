from django.db.models import Q

from core.models import Document, DocumentStatus, Dossier, UserRole


AUDITOR_VISIBLE_DOCUMENT_STATUSES = (
    DocumentStatus.PENDING,
    DocumentStatus.REJECTED,
    DocumentStatus.APPROVED,
)
READER_VISIBLE_DOCUMENT_STATUSES = (DocumentStatus.APPROVED,)
FULL_DOCUMENT_STATUS_SET = {
    DocumentStatus.DRAFT,
    DocumentStatus.PENDING,
    DocumentStatus.REJECTED,
    DocumentStatus.APPROVED,
}
BOOLEAN_TRUE_VALUES = {"true", "1"}
BOOLEAN_FALSE_VALUES = {"false", "0"}


def _get_clean_param(params, key):
    if params is None:
        return None
    value = params.get(key)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _filter_user_reference(queryset, field_name, raw_value):
    if raw_value.isdigit():
        return queryset.filter(**{f"{field_name}_id": int(raw_value)})
    return queryset.filter(**{f"{field_name}__username__icontains": raw_value})


def get_allowed_status_filters_for_user(user):
    if not user or not user.is_authenticated:
        return set()
    if user.role in {UserRole.ADMIN, UserRole.DATA_ENTRY}:
        return FULL_DOCUMENT_STATUS_SET
    if user.role == UserRole.AUDITOR:
        return set(AUDITOR_VISIBLE_DOCUMENT_STATUSES)
    if user.role == UserRole.READER:
        return set(READER_VISIBLE_DOCUMENT_STATUSES)
    return set()


def get_document_visibility_queryset(user):
    if not user or not user.is_authenticated:
        return Document.objects.none()

    queryset = Document.objects.filter(is_deleted=False)

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
    return Document.objects.none()


def get_dossier_visibility_queryset(user):
    if not user or not user.is_authenticated:
        return Dossier.objects.none()

    queryset = Dossier.objects.all()

    if user.role == UserRole.ADMIN:
        return queryset
    if user.role == UserRole.DATA_ENTRY:
        return queryset.filter(created_by=user)
    if user.role == UserRole.AUDITOR:
        return queryset.filter(
            created_by__assigned_auditor=user,
            documents__is_deleted=False,
            documents__created_by__assigned_auditor=user,
            documents__status__in=AUDITOR_VISIBLE_DOCUMENT_STATUSES,
        ).distinct()
    if user.role == UserRole.READER:
        return queryset.filter(
            documents__is_deleted=False,
            documents__status=DocumentStatus.APPROVED,
        ).distinct()
    return Dossier.objects.none()


def apply_document_advanced_filters(queryset, params, user):
    if params is None:
        return queryset

    search = _get_clean_param(params, "search")
    if search:
        queryset = queryset.filter(
            Q(doc_number__icontains=search)
            | Q(doc_name__icontains=search)
            | Q(file_path__icontains=search)
            | Q(dossier__file_number__icontains=search)
        )

    is_deleted = _get_clean_param(params, "is_deleted")
    if is_deleted and is_deleted.lower() in BOOLEAN_TRUE_VALUES:
        return queryset.none()

    status_value = _get_clean_param(params, "status")
    if status_value:
        allowed_statuses = get_allowed_status_filters_for_user(user)
        if status_value not in allowed_statuses:
            return queryset.none()
        queryset = queryset.filter(status=status_value)

    doc_type = _get_clean_param(params, "doc_type")
    if doc_type and doc_type.isdigit():
        queryset = queryset.filter(doc_type_id=int(doc_type))

    dossier = _get_clean_param(params, "dossier")
    if dossier:
        if dossier.isdigit():
            queryset = queryset.filter(dossier_id=int(dossier))
        else:
            queryset = queryset.filter(dossier__file_number__icontains=dossier)

    created_by = _get_clean_param(params, "created_by")
    if created_by:
        queryset = _filter_user_reference(queryset, "created_by", created_by)

    reviewed_by = _get_clean_param(params, "reviewed_by")
    if reviewed_by:
        if reviewed_by.lower() == "null":
            queryset = queryset.filter(reviewed_by__isnull=True)
        else:
            queryset = _filter_user_reference(queryset, "reviewed_by", reviewed_by)

    return queryset


def apply_dossier_advanced_filters(queryset, params, user):
    if params is None:
        return queryset

    search = _get_clean_param(params, "search")
    if search:
        queryset = queryset.filter(
            Q(file_number__icontains=search)
            | Q(full_name__icontains=search)
            | Q(national_id__icontains=search)
            | Q(personal_id__icontains=search)
        )

    governorate = _get_clean_param(params, "governorate")
    if governorate and governorate.isdigit():
        queryset = queryset.filter(governorate_id=int(governorate))

    created_by = _get_clean_param(params, "created_by")
    if created_by:
        queryset = _filter_user_reference(queryset, "created_by", created_by)

    is_deleted = _get_clean_param(params, "is_deleted")
    if is_deleted:
        lowered = is_deleted.lower()
        if lowered in BOOLEAN_TRUE_VALUES:
            queryset = queryset.filter(is_archived=True)
        elif lowered in BOOLEAN_FALSE_VALUES:
            queryset = queryset.filter(is_archived=False)

    return queryset


def get_document_queryset_for_user(user, *, deleted_state=False):
    queryset = get_document_visibility_queryset(user)
    if deleted_state:
        return queryset.none()
    return queryset


def get_document_detail_queryset_for_user(user):
    return get_document_visibility_queryset(user)


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
    if user.role not in {UserRole.ADMIN, UserRole.AUDITOR}:
        return Document.objects.none()
    return get_document_visibility_queryset(user).filter(status=DocumentStatus.PENDING)


def get_dossier_queryset_for_user(user):
    return get_dossier_visibility_queryset(user)


def get_dossier_documents_for_user(user, dossier):
    return get_document_visibility_queryset(user).filter(dossier=dossier)
