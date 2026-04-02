import re
import unicodedata

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import Max
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from django.utils.text import slugify

from core.access import get_document_edit_denial_reason, get_dossier_documents_for_user
from core.dossier_validation import normalize_text_value, validate_dossier_identity_data
from core.models import AuditAction, AuditLog, Document, DocumentStatus, DocumentType, Dossier, Governorate, UserRole
from core.services.audit_log_service import create_audit_log
from core.services.document_storage_service import (
    DocumentFileReplacementError,
    DocumentUploadError,
    delete_uploaded_pdf,
    replace_document_pdf,
    store_uploaded_pdf,
    validate_uploaded_pdf,
)
from core.services.dossier_service import DossierCreationError, create_dossier_with_first_document
from core.user_visibility import get_operational_user_queryset

User = get_user_model()

ROLE_CHANGE_BLOCKING_DOCUMENT_STATUSES = (
    DocumentStatus.DRAFT,
    DocumentStatus.REJECTED,
    DocumentStatus.PENDING,
)
DATA_ENTRY_ROLE_CHANGE_BLOCKED_MESSAGE = (
    "لا يمكن تغيير دور هذا المستخدم لأنه يملك وثائق غير منتهية (مسودة / مرفوضة / قيد المراجعة)."
)
AUDITOR_ROLE_CHANGE_BLOCKED_MESSAGE = "لا يمكن تغيير دور هذا المدقق لأنه ما زال مرتبطًا بمدخلي بيانات."


class MinimalUserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "full_name", "role")

    def get_full_name(self, obj):
        full_name = f"{obj.first_name or ''} {obj.last_name or ''}".strip()
        return full_name or None


class MeSerializer(serializers.ModelSerializer):
    assigned_auditor_id = serializers.PrimaryKeyRelatedField(
        source="assigned_auditor",
        queryset=get_operational_user_queryset().filter(role=UserRole.AUDITOR),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = User
        fields = ("id", "username", "first_name", "last_name", "email", "is_active", "role", "assigned_auditor_id")


class UserManagementSerializer(serializers.ModelSerializer):
    """Admin-only serializer for user CRUD with assigned_auditor linkage."""
    full_name = serializers.SerializerMethodField()
    assigned_auditor = MinimalUserSerializer(read_only=True)
    assigned_auditor_id = serializers.PrimaryKeyRelatedField(
        source="assigned_auditor",
        queryset=get_operational_user_queryset().filter(role=UserRole.AUDITOR),
        required=False,
        allow_null=True,
    )
    assigned_auditor_username = serializers.CharField(source="assigned_auditor.username", read_only=True)
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "full_name",
            "password",
            "first_name",
            "last_name",
            "email",
            "is_active",
            "role",
            "assigned_auditor",
            "assigned_auditor_id",
            "assigned_auditor_username",
            "date_joined",
        )
        read_only_fields = ("date_joined",)

    def validate_role_change(self, next_role):
        if self.instance is None:
            return

        current_role = self.instance.role
        if current_role == next_role:
            return

        if current_role == UserRole.DATA_ENTRY:
            has_blocking_documents = self.instance.created_documents.filter(
                status__in=ROLE_CHANGE_BLOCKING_DOCUMENT_STATUSES,
                is_deleted=False,
            ).exists()
            if has_blocking_documents:
                raise serializers.ValidationError({"role": DATA_ENTRY_ROLE_CHANGE_BLOCKED_MESSAGE})

        if current_role == UserRole.AUDITOR:
            has_assigned_data_entries = self.instance.assigned_data_entries.filter(role=UserRole.DATA_ENTRY).exists()
            if has_assigned_data_entries:
                raise serializers.ValidationError({"role": AUDITOR_ROLE_CHANGE_BLOCKED_MESSAGE})

    def validate(self, data):
        role = data.get("role") or getattr(self.instance, "role", None)
        assigned_auditor = data.get("assigned_auditor", getattr(self.instance, "assigned_auditor", None))
        if self.instance is None and not data.get("password"):
            raise serializers.ValidationError({"password": "Password is required when creating a user."})
        self.validate_role_change(role)
        if role != UserRole.DATA_ENTRY:
            data["assigned_auditor"] = None
            return data
        if assigned_auditor is None:
            raise serializers.ValidationError({"assigned_auditor_id": "Assigned reviewer is required for data entry users."})
        return data

    def get_full_name(self, obj):
        full_name = f"{obj.first_name or ''} {obj.last_name or ''}".strip()
        return full_name or None

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = super().create(validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user

    def update(self, instance, validated_data):
        actor = self.context["request"].user
        old_role = instance.role
        old_assigned_auditor_id = instance.assigned_auditor_id
        old_assigned_auditor_username = instance.assigned_auditor.username if instance.assigned_auditor else None
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save()

        if old_role != user.role:
            create_audit_log(
                user=actor,
                action=AuditAction.UPDATE,
                entity_type="user",
                entity_id=user.id,
                old_values={"role": old_role},
                new_values={
                    "role": user.role,
                    "message": f"Changed role from {old_role} to {user.role}.",
                },
            )

        if old_assigned_auditor_id != user.assigned_auditor_id:
            new_assigned_auditor_username = user.assigned_auditor.username if user.assigned_auditor else None
            if old_assigned_auditor_id is None and user.assigned_auditor_id is not None:
                message = f"Assigned reviewer {new_assigned_auditor_username}."
            elif old_assigned_auditor_id is not None and user.assigned_auditor_id is None:
                message = "Cleared the assigned reviewer."
            else:
                message = (
                    f"Reassigned reviewer from {old_assigned_auditor_username} "
                    f"to {new_assigned_auditor_username}."
                )

            create_audit_log(
                user=actor,
                action=AuditAction.UPDATE,
                entity_type="user",
                entity_id=user.id,
                old_values={
                    "assigned_auditor_by": old_assigned_auditor_id,
                    "assigned_auditor_username": old_assigned_auditor_username,
                },
                new_values={
                    "assigned_auditor_by": user.assigned_auditor_id,
                    "assigned_auditor_username": new_assigned_auditor_username,
                    "message": message,
                },
            )
        return user


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def save(self, **kwargs):
        token = self.validated_data["refresh"]
        try:
            RefreshToken(token).blacklist()
        except TokenError as exc:
            raise serializers.ValidationError({"refresh": "Invalid or expired refresh token."}) from exc


class GovernorateLookupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Governorate
        fields = ("id", "name")


class DocumentTypeLookupSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentType
        fields = ("id", "name")


class DocumentTypeManagementSerializer(serializers.ModelSerializer):
    usage_count = serializers.SerializerMethodField()
    name = serializers.CharField(
        max_length=100,
        error_messages={
            "blank": "اسم نوع الوثيقة مطلوب.",
            "required": "اسم نوع الوثيقة مطلوب.",
        },
    )

    class Meta:
        model = DocumentType
        fields = (
            "id",
            "name",
            "is_active",
            "usage_count",
        )
        read_only_fields = ("usage_count",)

    def get_usage_count(self, obj):
        annotated_count = getattr(obj, "usage_count", None)
        if annotated_count is not None:
            return annotated_count
        return obj.documents.count()

    def validate_name(self, value):
        cleaned_name = clean_document_type_name(value)
        if not cleaned_name:
            raise serializers.ValidationError("اسم نوع الوثيقة مطلوب.")

        normalized_name = normalize_document_type_name(cleaned_name)
        queryset = DocumentType.objects.all()
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)

        for existing_name in queryset.values_list("name", flat=True):
            if normalize_document_type_name(existing_name) == normalized_name:
                raise serializers.ValidationError("يوجد نوع وثيقة بالاسم نفسه بالفعل.")

        return cleaned_name

    def create(self, validated_data):
        max_order = DocumentType.objects.aggregate(max_order=Max("display_order"))["max_order"] or 0
        document_type = DocumentType.objects.create(
            slug=build_document_type_slug(validated_data["name"]),
            group_name="أنواع مضافة",
            display_order=max_order + 1,
            **validated_data,
        )
        create_audit_log(
            user=self.context["request"].user,
            action=AuditAction.CREATE,
            entity_type="document_type",
            entity_id=document_type.id,
            old_values=None,
            new_values={
                "name": document_type.name,
                "is_active": document_type.is_active,
            },
        )
        return document_type

    def update(self, instance, validated_data):
        old_values = {
            "name": instance.name,
            "is_active": instance.is_active,
        }
        if "name" in validated_data:
            validated_data["slug"] = build_document_type_slug(validated_data["name"], existing_slug=instance.slug)
        document_type = super().update(instance, validated_data)
        create_audit_log(
            user=self.context["request"].user,
            action=AuditAction.UPDATE,
            entity_type="document_type",
            entity_id=document_type.id,
            old_values=old_values,
            new_values={
                "name": document_type.name,
                "is_active": document_type.is_active,
            },
        )
        return document_type


class DocumentRejectSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField(max_length=2000)


AUDIT_ACTION_LABELS = {
    AuditAction.CREATE: "إنشاء",
    AuditAction.UPDATE: "تحديث",
    AuditAction.SUBMIT: "تقديم",
    AuditAction.APPROVE: "موافقة",
    AuditAction.REJECT: "رفض",
    AuditAction.REPLACE_FILE: "استبدال الملف",
    AuditAction.DELETE: "حذف",
    AuditAction.RESTORE: "استعادة",
    AuditAction.LOGIN: "تسجيل الدخول",
    AuditAction.LOGIN_FAILED: "فشل تسجيل الدخول",
    AuditAction.LOGOUT: "تسجيل الخروج",
    AuditAction.REFRESH_FAILED: "فشل تحديث الجلسة",
    AuditAction.ACCESS_DENIED: "رفض أمني",
}
AUDIT_ENTITY_LABELS = {
    "document": "وثيقة",
    "dossier": "إضبارة",
    "user": "مستخدم",
    "document_type": "نوع وثيقة",
}
AUDIT_CHANGE_FIELD_LABELS = {
    "status": "الحالة",
    "doc_name": "اسم الوثيقة",
    "doc_number": "رقم الوثيقة",
    "file_number": "رقم الإضبارة",
    "full_name": "الاسم",
    "role": "الدور",
    "rejection_reason": "سبب الرفض",
    "name": "اسم نوع الوثيقة",
    "is_active": "الحالة",
    "assigned_auditor_username": "المدقق المعيّن",
}


DOCUMENT_STATUS_LABELS = {
    DocumentStatus.DRAFT: "مسودة",
    DocumentStatus.PENDING: "قيد المراجعة",
    DocumentStatus.APPROVED: "معتمدة",
    DocumentStatus.REJECTED: "مرفوضة",
}


ARABIC_NORMALIZATION_MAP = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ؤ": "ي",
        "ئ": "ي",
        "ة": "ه",
    }
)


def clean_document_type_name(value):
    return re.sub(r"\s+", " ", (value or "")).strip()


def normalize_document_type_name(value):
    cleaned = clean_document_type_name(value)
    normalized = unicodedata.normalize("NFKC", cleaned)
    normalized = normalized.translate(ARABIC_NORMALIZATION_MAP)
    normalized = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    )
    return normalized.casefold()


def build_document_type_slug(name, *, existing_slug=None):
    if existing_slug:
        return existing_slug

    base_slug = slugify(clean_document_type_name(name), allow_unicode=True) or "document-type"
    candidate = base_slug
    suffix = 2

    while DocumentType.objects.filter(slug=candidate).exists():
        candidate = f"{base_slug}-{suffix}"
        suffix += 1

    return candidate


def validate_active_document_type_selection(document_type, *, allow_inactive_instance_id=None):
    if document_type.is_active:
        return document_type

    if allow_inactive_instance_id is not None and document_type.id == allow_inactive_instance_id:
        return document_type

    raise serializers.ValidationError("نوع الوثيقة غير نشط حاليًا ولا يمكن اختياره.")


def get_user_full_name(user):
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return full_name or None


def get_user_display_name(user):
    return get_user_full_name(user) or user.username


def join_human_parts(*parts):
    clean_parts = [str(part).strip() for part in parts if part is not None and str(part).strip()]
    if not clean_parts:
        return None
    return " - ".join(clean_parts)


class AuditActorSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "role", "full_name", "display_name")

    def get_full_name(self, obj):
        return get_user_full_name(obj)

    def get_display_name(self, obj):
        return get_user_display_name(obj)


class AuditLogSerializer(serializers.ModelSerializer):
    actor = AuditActorSerializer(source="user", read_only=True)
    action_label = serializers.SerializerMethodField()
    entity_label = serializers.SerializerMethodField()
    entity_display = serializers.SerializerMethodField()
    entity_reference = serializers.SerializerMethodField()
    change_summary = serializers.SerializerMethodField()
    related_users = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "action",
            "action_label",
            "entity_type",
            "entity_label",
            "entity_id",
            "entity_display",
            "entity_reference",
            "change_summary",
            "old_values",
            "new_values",
            "related_users",
            "ip_address",
            "created_at",
            "actor",
        )

    def get_action_label(self, obj):
        return getattr(obj, "action_label_value", None) or AUDIT_ACTION_LABELS.get(obj.action, obj.action)

    def get_entity_label(self, obj):
        return getattr(obj, "entity_label_value", None) or AUDIT_ENTITY_LABELS.get(obj.entity_type, obj.entity_type)

    def get_entity_display(self, obj):
        annotated_display = getattr(obj, "entity_display_value", None)
        if annotated_display:
            cleaned = annotated_display.strip()
            if cleaned:
                return cleaned

        try:
            if obj.entity_type == "document":
                document = (
                    Document.objects.filter(id=obj.entity_id)
                    .select_related("dossier")
                    .values("doc_name", "doc_number", "dossier__file_number")
                    .first()
                )
                if document:
                    return join_human_parts(
                        document["doc_name"],
                        document["doc_number"],
                        document["dossier__file_number"],
                    )
            elif obj.entity_type == "dossier":
                dossier = Dossier.objects.filter(id=obj.entity_id).values("full_name", "file_number").first()
                if dossier:
                    return join_human_parts(dossier["full_name"], dossier["file_number"])
            elif obj.entity_type == "user":
                entity_user = User.objects.filter(id=obj.entity_id).first()
                if entity_user:
                    return join_human_parts(get_user_full_name(entity_user), entity_user.username)
            elif obj.entity_type == "document_type":
                document_type = DocumentType.objects.filter(id=obj.entity_id).values("name").first()
                if document_type:
                    return document_type["name"]
        except Exception:
            return None

        return None

    def get_entity_reference(self, obj):
        """Backward-compatible short reference used by the detail page."""
        try:
            if obj.entity_type == "document":
                doc = (
                    Document.objects.filter(id=obj.entity_id)
                    .select_related("doc_type")
                    .values("doc_type__name", "doc_number")
                    .first()
                )
                if doc:
                    return join_human_parts(doc["doc_type__name"], doc["doc_number"])
            elif obj.entity_type == "dossier":
                dossier = Dossier.objects.filter(id=obj.entity_id).values("file_number").first()
                if dossier:
                    return dossier["file_number"]
            elif obj.entity_type == "user":
                user = User.objects.filter(id=obj.entity_id).values("username").first()
                if user:
                    return user["username"]
            elif obj.entity_type == "document_type":
                document_type = DocumentType.objects.filter(id=obj.entity_id).values("name").first()
                if document_type:
                    return document_type["name"]
        except Exception:
            pass
        return None

    def get_change_summary(self, obj):
        action_label = self.get_action_label(obj)
        entity_label = self.get_entity_label(obj)
        entity_display = self.get_entity_display(obj)
        old_values = obj.old_values or {}
        new_values = obj.new_values or {}

        summary_parts = [f"{action_label} {entity_label}"]
        if entity_display:
            summary_parts.append(entity_display)

        if obj.action == AuditAction.RESTORE and old_values.get("is_deleted") is True and new_values.get("is_deleted") is False:
            summary_parts.append("أُعيدت إلى القوائم النشطة")
            return " - ".join(summary_parts)

        message = new_values.get("message") or old_values.get("message")
        if isinstance(message, str) and message.strip():
            summary_parts.append(message.strip())
            return " - ".join(summary_parts)

        rejection_reason = new_values.get("rejection_reason") or old_values.get("rejection_reason")
        if isinstance(rejection_reason, str) and rejection_reason.strip():
            summary_parts.append(rejection_reason.strip())
            return " - ".join(summary_parts)

        new_status = new_values.get("status")
        old_status = old_values.get("status")
        if new_status and new_status != old_status:
            summary_parts.append(f"الحالة: {new_status}")
            return " - ".join(summary_parts)

        changed_fields = [
            AUDIT_CHANGE_FIELD_LABELS.get(key, key)
            for key in new_values.keys()
            if old_values.get(key) != new_values.get(key)
        ]
        if changed_fields:
            summary_parts.append(f"تم تحديث {', '.join(changed_fields[:3])}")

        return " - ".join(summary_parts)

    def get_related_users(self, obj):
        user_ids = set()

        def collect_user_ids(value):
            if isinstance(value, dict):
                for key, nested_value in value.items():
                    if key.endswith("_by") and isinstance(nested_value, int):
                        user_ids.add(nested_value)
                    else:
                        collect_user_ids(nested_value)
            elif isinstance(value, list):
                for item in value:
                    collect_user_ids(item)

        collect_user_ids(obj.old_values or {})
        collect_user_ids(obj.new_values or {})

        if not user_ids:
            return {}

        users_by_id = {user.id: user for user in User.objects.filter(id__in=user_ids)}
        serializer = AuditActorSerializer([users_by_id[user_id] for user_id in user_ids if user_id in users_by_id], many=True)
        return {str(item["id"]): item for item in serializer.data}


class DocumentSummarySerializer(serializers.ModelSerializer):
    is_approved_by_admin = serializers.SerializerMethodField()
    is_rejected_by_admin = serializers.SerializerMethodField()
    status_display_label = serializers.SerializerMethodField()
    can_add_another_document = serializers.SerializerMethodField()
    dossier_name = serializers.CharField(source="dossier.file_number", read_only=True)
    doc_type_name = serializers.CharField(source="doc_type.name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.username", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.username", read_only=True)
    reviewed_by_role = serializers.CharField(source="reviewed_by.role", read_only=True)
    deleted_by_name = serializers.CharField(source="deleted_by.username", read_only=True)

    class Meta:
        model = Document
        fields = (
            "id",
            "dossier",
            "dossier_name",
            "doc_type",
            "doc_type_name",
            "doc_number",
            "doc_name",
            "file_path",
            "file_size_kb",
            "mime_type",
            "status",
            "status_display_label",
            "notes",
            "created_by",
            "created_by_name",
            "reviewed_by",
            "reviewed_by_name",
            "reviewed_by_role",
            "created_at",
            "updated_at",
            "submitted_at",
            "reviewed_at",
            "rejection_reason",
            "is_deleted",
            "deleted_at",
            "deleted_by_name",
            "is_approved_by_admin",
            "is_rejected_by_admin",
            "can_add_another_document",
        )

    def get_is_approved_by_admin(self, obj):
        """
        Returns True when the current approved state was set by an admin user.
        """
        if obj.status != DocumentStatus.APPROVED:
            return False
        if not obj.reviewed_by:
            return False
        return obj.reviewed_by.role == UserRole.ADMIN

    def get_is_rejected_by_admin(self, obj):
        """
        Returns True when the current rejected state was set by an admin user.
        """
        if obj.status != DocumentStatus.REJECTED:
            return False
        if not obj.reviewed_by:
            return False
        return obj.reviewed_by.role == UserRole.ADMIN

    def get_status_display_label(self, obj):
        if self.get_is_approved_by_admin(obj):
            return "معتمدة من المدير"
        if self.get_is_rejected_by_admin(obj):
            return "مرفوضة من المدير"
        return DOCUMENT_STATUS_LABELS.get(obj.status, obj.status)

    def get_can_add_another_document(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        dossier = getattr(obj, "dossier", None)

        if not user or not getattr(user, "is_authenticated", False) or dossier is None or dossier.is_archived:
            return False

        if user.role == UserRole.ADMIN:
            return True

        return user.role == UserRole.DATA_ENTRY and dossier.created_by_id == user.id


class AdminDashboardRecentDocumentSerializer(serializers.ModelSerializer):
    dossier_name = serializers.CharField(source="dossier.file_number", read_only=True)
    doc_type_name = serializers.CharField(source="doc_type.name", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = (
            "id",
            "doc_number",
            "doc_name",
            "dossier_name",
            "doc_type_name",
            "status",
            "status_label",
            "created_by_name",
            "reviewed_by_name",
            "created_at",
            "submitted_at",
            "reviewed_at",
            "rejection_reason",
        )

    def get_created_by_name(self, obj):
        return get_user_display_name(obj.created_by)

    def get_reviewed_by_name(self, obj):
        if not obj.reviewed_by:
            return None
        return get_user_display_name(obj.reviewed_by)

    def get_status_label(self, obj):
        if obj.status == DocumentStatus.APPROVED and obj.reviewed_by and obj.reviewed_by.role == UserRole.ADMIN:
            return "معتمدة من المدير"
        if obj.status == DocumentStatus.REJECTED and obj.reviewed_by and obj.reviewed_by.role == UserRole.ADMIN:
            return "مرفوضة من المدير"
        return DOCUMENT_STATUS_LABELS.get(obj.status, obj.status)


class AdminDashboardAuditEventSerializer(AuditLogSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta(AuditLogSerializer.Meta):
        fields = (
            "id",
            "action_label",
            "entity_label",
            "entity_display",
            "change_summary",
            "created_at",
            "actor_name",
        )

    def get_actor_name(self, obj):
        annotated_name = getattr(obj, "actor_display_name_value", None)
        if annotated_name:
            return annotated_name
        return get_user_display_name(obj.user)


class AdminDashboardDataEntryPerformanceSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    display_name = serializers.CharField()
    assigned_auditor_name = serializers.CharField(allow_null=True)
    dossiers_created_count = serializers.IntegerField()
    documents_created_count = serializers.IntegerField()
    draft_documents_count = serializers.IntegerField()
    pending_documents_count = serializers.IntegerField()
    rejected_documents_count = serializers.IntegerField()
    approved_documents_count = serializers.IntegerField()
    submissions_count = serializers.IntegerField()
    last_activity_at = serializers.DateTimeField(allow_null=True)


class AdminDashboardAuditorPerformanceSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    display_name = serializers.CharField()
    assigned_data_entry_count = serializers.IntegerField()
    pending_documents_in_scope = serializers.IntegerField()
    rejected_documents_in_scope = serializers.IntegerField()
    reviewed_documents_count = serializers.IntegerField()
    approved_by_auditor_count = serializers.IntegerField()
    rejected_by_auditor_count = serializers.IntegerField()
    last_activity_at = serializers.DateTimeField(allow_null=True)


class AdminDashboardAdminReviewActivitySerializer(serializers.Serializer):
    approved_by_admin_count = serializers.IntegerField()
    rejected_by_admin_count = serializers.IntegerField()
    latest_admin_review_at = serializers.DateTimeField(allow_null=True)


class DocumentCreateSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True, required=True)

    class Meta:
        model = Document
        fields = (
            "id",
            "dossier",
            "doc_type",
            "doc_number",
            "doc_name",
            "file_path",
            "file_size_kb",
            "mime_type",
            "notes",
            "file",
        )
        read_only_fields = ("id", "file_path", "file_size_kb", "mime_type")

    def validate_file(self, value):
        try:
            validate_uploaded_pdf(value)
        except DocumentUploadError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return value

    def validate_dossier(self, value):
        user = self.context["request"].user
        if value.is_archived:
            raise serializers.ValidationError("Cannot add documents to an archived dossier.")
        if user.role == UserRole.DATA_ENTRY and value.created_by_id != user.id:
            raise serializers.ValidationError("You can only add documents to dossiers you created.")
        return value

    def validate_doc_type(self, value):
        return validate_active_document_type_selection(value)

    def create(self, validated_data):
        user = self.context["request"].user
        uploaded_file = validated_data.pop("file")
        stored_file_data = store_uploaded_pdf(dossier_id=validated_data["dossier"].id, uploaded_file=uploaded_file)
        stored_file_path = stored_file_data["file_path"]
        document = Document(created_by=user, **validated_data, **stored_file_data)
        try:
            document.full_clean()
            document.save()
        except DjangoValidationError as exc:
            delete_uploaded_pdf(stored_file_path)
            raise serializers.ValidationError(exc.message_dict) from exc
        except IntegrityError as exc:
            delete_uploaded_pdf(stored_file_path)
            raise serializers.ValidationError({"non_field_errors": ["Failed to create document."]}) from exc

        create_audit_log(
            user=user,
            action=AuditAction.CREATE,
            entity_type="document",
            entity_id=document.id,
            old_values=None,
            new_values={"doc_number": document.doc_number, "status": document.status},
        )
        return document


class DocumentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = (
            "doc_type",
            "doc_number",
            "doc_name",
            "file_path",
            "file_size_kb",
            "mime_type",
            "notes",
        )

    def validate(self, attrs):
        denial_reason = get_document_edit_denial_reason(self.context["request"].user, self.instance)
        if denial_reason is not None:
            raise serializers.ValidationError({"status": denial_reason})
        return attrs

    def validate_doc_type(self, value):
        return validate_active_document_type_selection(value, allow_inactive_instance_id=self.instance.doc_type_id)

    def update(self, instance, validated_data):
        user = self.context["request"].user
        old_values = {
            "doc_number": instance.doc_number,
            "doc_name": instance.doc_name,
            "file_path": instance.file_path,
        }
        document = super().update(instance, validated_data)
        create_audit_log(
            user=user,
            action=AuditAction.UPDATE,
            entity_type="document",
            entity_id=document.id,
            old_values=old_values,
            new_values={
                "doc_number": document.doc_number,
                "doc_name": document.doc_name,
                "file_path": document.file_path,
            },
        )
        return document


class DocumentReplaceFileSerializer(serializers.Serializer):
    file = serializers.FileField(write_only=True, required=True)

    def validate_file(self, value):
        try:
            validate_uploaded_pdf(value)
        except DocumentUploadError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return value

    def validate(self, attrs):
        document = self.instance
        if document is None:
            return attrs
        if document.is_deleted:
            raise serializers.ValidationError({"detail": "Soft-deleted documents cannot be modified."})
        if document.status not in [DocumentStatus.DRAFT, DocumentStatus.REJECTED]:
            raise serializers.ValidationError(
                {"detail": "Document file can only be replaced when status is draft or rejected."}
            )
        return attrs

    def save(self, **kwargs):
        try:
            return replace_document_pdf(
                actor=self.context["request"].user,
                document=self.instance,
                uploaded_file=self.validated_data["file"],
            )
        except DocumentFileReplacementError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

class DossierListSerializer(serializers.ModelSerializer):
    governorate_name = serializers.CharField(source="governorate.name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.username", read_only=True)
    nationality_display = serializers.SerializerMethodField()

    class Meta:
        model = Dossier
        fields = (
            "id",
            "file_number",
            "full_name",
            "national_id",
            "personal_id",
            "is_non_syrian",
            "nationality_name",
            "nationality_display",
            "governorate",
            "governorate_name",
            "room_number",
            "column_number",
            "shelf_number",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
            "is_archived",
        )

    def get_nationality_display(self, obj):
        return obj.nationality_name or "سورية"


class DossierDetailSerializer(DossierListSerializer):
    documents = serializers.SerializerMethodField()

    class Meta(DossierListSerializer.Meta):
        fields = DossierListSerializer.Meta.fields + ("documents",)

    def get_documents(self, dossier):
        user = self.context["request"].user
        qs = get_dossier_documents_for_user(user, dossier)
        return DocumentSummarySerializer(qs, many=True).data

class FirstDocumentInputSerializer(serializers.Serializer):
    doc_type_id = serializers.PrimaryKeyRelatedField(queryset=DocumentType.objects.all(), source="doc_type")
    doc_number = serializers.CharField(max_length=100)
    doc_name = serializers.CharField(max_length=200)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)
    file = serializers.FileField(write_only=True, required=True)

    def validate_file(self, value):
        try:
            validate_uploaded_pdf(value)
        except DocumentUploadError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return value

    def validate_doc_type_id(self, value):
        return validate_active_document_type_selection(value)


class DossierCreateSerializer(serializers.Serializer):
    file_number = serializers.CharField(max_length=50)
    full_name = serializers.CharField(max_length=200)
    national_id = serializers.CharField(max_length=30)
    personal_id = serializers.CharField(max_length=30)
    is_non_syrian = serializers.BooleanField(required=False, default=False)
    nationality_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    governorate_id = serializers.IntegerField(required=False, allow_null=True)
    room_number = serializers.CharField(max_length=20)
    column_number = serializers.CharField(max_length=20)
    shelf_number = serializers.CharField(max_length=20)
    first_document = FirstDocumentInputSerializer(required=True)

    def validate(self, attrs):
        if not attrs.get("first_document"):
            raise serializers.ValidationError({"first_document": "First document is required; empty dossier creation is not allowed."})

        attrs["file_number"] = normalize_text_value(attrs["file_number"])
        attrs["full_name"] = normalize_text_value(attrs["full_name"])
        validation = validate_dossier_identity_data(
            is_non_syrian=attrs.get("is_non_syrian", False),
            nationality_name=attrs.get("nationality_name", ""),
            national_id=attrs.get("national_id", ""),
            personal_id=attrs.get("personal_id", ""),
            room_number=attrs.get("room_number", ""),
            column_number=attrs.get("column_number", ""),
            shelf_number=attrs.get("shelf_number", ""),
        )

        if validation["errors"]:
            raise serializers.ValidationError(validation["errors"])

        attrs.update(validation["normalized_values"])
        attrs["nationality_name"] = validation["normalized_nationality_name"]
        return attrs

    def create(self, validated_data):
        first_document_data = validated_data.pop("first_document", None)
        governorate_id = validated_data.pop("governorate_id", None)
        if governorate_id is not None:
            validated_data["governorate_id"] = governorate_id

        try:
            dossier, _ = create_dossier_with_first_document(
                actor=self.context["request"].user,
                dossier_data=validated_data,
                first_document_data=first_document_data,
            )
            return dossier
        except DossierCreationError as exc:
            raise serializers.ValidationError({"first_document": str(exc)}) from exc
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        except IntegrityError as exc:
            raise serializers.ValidationError({"non_field_errors": ["Failed to create dossier with first document atomically."]}) from exc

