from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

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
    assigned_auditor_id = serializers.PrimaryKeyRelatedField(
        source="assigned_auditor",
        queryset=User.objects.filter(role=UserRole.AUDITOR),
        required=False,
        allow_null=True,
    )
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "password",
            "first_name",
            "last_name",
            "email",
            "is_active",
            "role",
            "assigned_auditor_id",
            "date_joined",
        )
        read_only_fields = ("date_joined",)

    def validate(self, data):
        """Clear assigned_auditor if role is not data_entry."""
        role = data.get("role") or getattr(self.instance, "role", None)
        if role != UserRole.DATA_ENTRY:
            data["assigned_auditor"] = None
        return data

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


class AuditActorSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "role")


class AuditLogSerializer(serializers.ModelSerializer):
    actor = AuditActorSerializer(source="user", read_only=True)
    entity_reference = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "action",
            "entity_type",
            "entity_id",
            "entity_reference",
            "old_values",
            "new_values",
            "ip_address",
            "created_at",
            "actor",
        )

    def get_entity_reference(self, obj):
        """Return human-readable reference for the entity if available."""
        try:
            if obj.entity_type == "document":
                from core.models import Document
                doc = Document.objects.filter(id=obj.entity_id).select_related("doc_type").values("doc_number", "doc_name", "doc_type__name").first()
                if doc:
                    return doc["doc_type__name"] if doc["doc_type__name"] else None
            elif obj.entity_type == "dossier":
                from core.models import Dossier
                dossier = Dossier.objects.filter(id=obj.entity_id).values("file_number").first()
                if dossier:
                    return dossier["file_number"]
            elif obj.entity_type == "user":
                from core.models import User
                user = User.objects.filter(id=obj.entity_id).values("username").first()
                if user:
                    return user["username"]
        except Exception:
            pass
        return None


class DocumentSummarySerializer(serializers.ModelSerializer):
    is_approved_by_admin = serializers.SerializerMethodField()
    is_rejected_by_admin = serializers.SerializerMethodField()
    dossier_name = serializers.CharField(source="dossier.file_number", read_only=True)
    doc_type_name = serializers.CharField(source="doc_type.name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.username", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.username", read_only=True)

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
            "created_at",
            "updated_at",
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
        if value.is_archived:
            raise serializers.ValidationError("Cannot add documents to an archived dossier.")
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
        qs = dossier.documents.filter(is_deleted=False)
        if user.role == UserRole.READER:
            qs = qs.filter(status="approved")
        elif user.role == UserRole.AUDITOR:
            qs = qs.filter(status__in=["pending", "approved"])
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

