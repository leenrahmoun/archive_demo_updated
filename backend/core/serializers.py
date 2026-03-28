from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from core.access import get_dossier_documents_for_user
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
        queryset=User.objects.filter(role=UserRole.AUDITOR),
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
        queryset=User.objects.filter(role=UserRole.AUDITOR),
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
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save()
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
        fields = ("id", "name", "slug", "group_name", "display_order")


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
}
AUDIT_ENTITY_LABELS = {
    "document": "وثيقة",
    "dossier": "إضبارة",
    "user": "مستخدم",
}
AUDIT_CHANGE_FIELD_LABELS = {
    "status": "الحالة",
    "doc_name": "اسم الوثيقة",
    "doc_number": "رقم الوثيقة",
    "file_number": "رقم الإضبارة",
    "full_name": "الاسم",
    "role": "الدور",
    "rejection_reason": "سبب الرفض",
}


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


class DocumentSummarySerializer(serializers.ModelSerializer):
    is_approved_by_admin = serializers.SerializerMethodField()
    is_rejected_by_admin = serializers.SerializerMethodField()
    dossier_name = serializers.CharField(source="dossier.file_number", read_only=True)
    doc_type_name = serializers.CharField(source="doc_type.name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.username", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.username", read_only=True)
    reviewed_by_role = serializers.CharField(source="reviewed_by.role", read_only=True)

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
            "is_approved_by_admin",
            "is_rejected_by_admin",
        )

    def get_is_approved_by_admin(self, obj):
        """
        Returns True if document is approved and reviewed by an admin user,
        indicating that an admin approved a document in the auditor's scope.
        """
        if obj.status != DocumentStatus.APPROVED:
            return False
        if not obj.created_by:
            return False
        # Get the assigned auditor for the creator (if creator is data_entry)
        assigned_auditor_id = getattr(obj.created_by, "assigned_auditor_id", None)
        if not assigned_auditor_id:
            return False
        # Check if reviewer exists and is an admin
        if not obj.reviewed_by:
            return False
        return obj.reviewed_by.role == UserRole.ADMIN

    def get_is_rejected_by_admin(self, obj):
        """
        Returns True if document is rejected and reviewed by an admin user,
        indicating that an admin rejected a document in the auditor's scope.
        """
        if obj.status != DocumentStatus.REJECTED:
            return False
        if not obj.created_by:
            return False
        # Get the assigned auditor for the creator (if creator is data_entry)
        assigned_auditor_id = getattr(obj.created_by, "assigned_auditor_id", None)
        if not assigned_auditor_id:
            return False
        # Check if reviewer exists and is an admin
        if not obj.reviewed_by:
            return False
        return obj.reviewed_by.role == UserRole.ADMIN


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
        if self.instance.status not in [DocumentStatus.DRAFT, DocumentStatus.REJECTED]:
            raise serializers.ValidationError({"status": "Document can only be edited when it is in draft or rejected status."})
        return attrs

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

    class Meta:
        model = Dossier
        fields = (
            "id",
            "file_number",
            "full_name",
            "national_id",
            "personal_id",
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


class DossierCreateSerializer(serializers.Serializer):
    file_number = serializers.CharField(max_length=50)
    full_name = serializers.CharField(max_length=200)
    national_id = serializers.CharField(max_length=30)
    personal_id = serializers.CharField(max_length=30)
    governorate_id = serializers.IntegerField(required=False, allow_null=True)
    room_number = serializers.CharField(max_length=20)
    column_number = serializers.CharField(max_length=20)
    shelf_number = serializers.CharField(max_length=20)
    first_document = FirstDocumentInputSerializer(required=True)

    def validate(self, attrs):
        if not attrs.get("first_document"):
            raise serializers.ValidationError({"first_document": "First document is required; empty dossier creation is not allowed."})
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

