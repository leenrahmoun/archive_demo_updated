from django.db.models import Case, CharField, F, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Cast, Coalesce, Concat, Trim
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from core.models import AuditAction, AuditLog, Document, DocumentStatus, Dossier, User, UserRole


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
AUDIT_ACTION_LABELS = {
    AuditAction.CREATE: "إنشاء",
    AuditAction.UPDATE: "تحديث",
    AuditAction.SUBMIT: "تقديم",
    AuditAction.APPROVE: "موافقة",
    AuditAction.REJECT: "رفض",
    AuditAction.REPLACE_FILE: "استبدال الملف",
    AuditAction.DELETE: "حذف",
    AuditAction.RESTORE: "استعادة",
}
AUDIT_ENTITY_LABELS = {
    "document": "وثيقة",
    "dossier": "إضبارة",
    "user": "مستخدم",
}


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


def get_audit_log_visibility_queryset(user):
    if not user or not user.is_authenticated:
        return AuditLog.objects.none()
    if user.role == UserRole.ADMIN:
        return AuditLog.objects.select_related("user").all()
    return AuditLog.objects.none()


def annotate_audit_log_human_fields(queryset):
    document_reference = Document.objects.filter(pk=OuterRef("entity_id")).annotate(
        reference=Trim(
            Concat(
                Coalesce("doc_name", Value("")),
                Value(" "),
                Coalesce("doc_number", Value("")),
                Value(" "),
                Coalesce("dossier__file_number", Value("")),
            )
        )
    ).values("reference")[:1]
    dossier_reference = Dossier.objects.filter(pk=OuterRef("entity_id")).annotate(
        reference=Trim(
            Concat(
                Coalesce("full_name", Value("")),
                Value(" "),
                Coalesce("file_number", Value("")),
            )
        )
    ).values("reference")[:1]
    user_reference = User.objects.filter(pk=OuterRef("entity_id")).annotate(
        reference=Trim(
            Concat(
                Coalesce("first_name", Value("")),
                Value(" "),
                Coalesce("last_name", Value("")),
                Value(" "),
                Coalesce("username", Value("")),
            )
        )
    ).values("reference")[:1]

    queryset = queryset.annotate(
        actor_full_name=Trim(
            Concat(
                Coalesce("user__first_name", Value("")),
                Value(" "),
                Coalesce("user__last_name", Value("")),
            )
        ),
        old_values_text=Coalesce(Cast("old_values", output_field=CharField()), Value("")),
        new_values_text=Coalesce(Cast("new_values", output_field=CharField()), Value("")),
    )
    queryset = queryset.annotate(
        actor_display_name_value=Case(
            When(actor_full_name="", then=F("user__username")),
            default=F("actor_full_name"),
            output_field=CharField(),
        ),
        action_label_value=Case(
            *[When(action=action, then=Value(label)) for action, label in AUDIT_ACTION_LABELS.items()],
            default=F("action"),
            output_field=CharField(),
        ),
        entity_label_value=Case(
            *[When(entity_type=entity_type, then=Value(label)) for entity_type, label in AUDIT_ENTITY_LABELS.items()],
            default=F("entity_type"),
            output_field=CharField(),
        ),
        entity_display_value=Case(
            When(entity_type="document", then=Coalesce(Subquery(document_reference), Value(""))),
            When(entity_type="dossier", then=Coalesce(Subquery(dossier_reference), Value(""))),
            When(entity_type="user", then=Coalesce(Subquery(user_reference), Value(""))),
            default=Value(""),
            output_field=CharField(),
        ),
    )
    return queryset.annotate(
        search_summary_value=Trim(
            Concat(
                Coalesce("user__username", Value("")),
                Value(" "),
                Coalesce(F("actor_full_name"), Value("")),
                Value(" "),
                Coalesce(F("action_label_value"), Value("")),
                Value(" "),
                Coalesce(F("entity_label_value"), Value("")),
                Value(" "),
                Coalesce(F("entity_display_value"), Value("")),
                Value(" "),
                Coalesce(F("old_values_text"), Value("")),
                Value(" "),
                Coalesce(F("new_values_text"), Value("")),
            )
        )
    )


def apply_audit_log_filters(queryset, params):
    if params is None:
        return queryset

    action = _get_clean_param(params, "action")
    if action:
        allowed_actions = {choice for choice, _ in AuditAction.choices}
        if action not in allowed_actions:
            return queryset.none()
        queryset = queryset.filter(action=action)

    date_from = _get_clean_param(params, "date_from")
    if date_from:
        parsed = parse_datetime(date_from)
        if parsed is None:
            parsed_date = parse_date(date_from)
            if parsed_date is not None:
                queryset = queryset.filter(created_at__date__gte=parsed_date)
        else:
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
            queryset = queryset.filter(created_at__gte=parsed)

    date_to = _get_clean_param(params, "date_to")
    if date_to:
        parsed = parse_datetime(date_to)
        if parsed is None:
            parsed_date = parse_date(date_to)
            if parsed_date is not None:
                queryset = queryset.filter(created_at__date__lte=parsed_date)
        else:
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
            queryset = queryset.filter(created_at__lte=parsed)

    return queryset


def apply_audit_log_search(queryset, params):
    search = _get_clean_param(params, "search")
    if not search:
        return queryset

    return queryset.filter(
        Q(user__username__icontains=search)
        | Q(actor_full_name__icontains=search)
        | Q(actor_display_name_value__icontains=search)
        | Q(action__icontains=search)
        | Q(action_label_value__icontains=search)
        | Q(entity_label_value__icontains=search)
        | Q(entity_display_value__icontains=search)
        | Q(search_summary_value__icontains=search)
    )


def get_document_visibility_queryset(user, *, deleted_state=False):
    if not user or not user.is_authenticated:
        return Document.objects.none()

    queryset = Document.objects.filter(is_deleted=deleted_state)

    if user.role == UserRole.ADMIN:
        return queryset
    if user.role == UserRole.DATA_ENTRY:
        return queryset.filter(created_by=user)
    if deleted_state:
        return Document.objects.none()
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


def apply_document_advanced_filters(queryset, params, user, *, deleted_state=False):
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

    deleted_filter = _get_clean_param(params, "is_deleted")
    if deleted_state:
        if deleted_filter and deleted_filter.lower() in BOOLEAN_FALSE_VALUES:
            return queryset.none()
    elif deleted_filter and deleted_filter.lower() in BOOLEAN_TRUE_VALUES:
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

    if deleted_state:
        deleted_by = _get_clean_param(params, "deleted_by")
        if deleted_by:
            queryset = _filter_user_reference(queryset, "deleted_by", deleted_by)

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

    archived_state = _get_clean_param(params, "is_archived") or _get_clean_param(params, "is_deleted")
    if archived_state:
        lowered = archived_state.lower()
        if lowered in BOOLEAN_TRUE_VALUES:
            queryset = queryset.filter(is_archived=True)
        elif lowered in BOOLEAN_FALSE_VALUES:
            queryset = queryset.filter(is_archived=False)

    return queryset


def get_document_queryset_for_user(user, *, deleted_state=False):
    return get_document_visibility_queryset(user, deleted_state=deleted_state)


def get_document_detail_queryset_for_user(user, *, deleted_state=False):
    return get_document_visibility_queryset(user, deleted_state=deleted_state)


def get_deleted_document_visibility_queryset(user):
    return get_document_visibility_queryset(user, deleted_state=True)


def get_deleted_document_detail_queryset_for_user(user):
    return get_document_detail_queryset_for_user(user, deleted_state=True)


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
