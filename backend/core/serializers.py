from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from core.models import AuditAction, AuditLog, Document, DocumentStatus, DocumentType, Dossier, Governorate, UserRole
from core.services.dossier_service import DossierCreationError, create_dossier_with_first_document

User = get_user_model()


class MeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "first_name", "last_name", "email", "is_active", "role")


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

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "action",
            "entity_type",
            "entity_id",
            "old_values",
            "new_values",
            "ip_address",
            "created_at",
            "actor",
        )


class DocumentSummarySerializer(serializers.ModelSerializer):
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
            "status",
            "notes",
            "created_by",
            "created_at",
            "updated_at",
        )


class DocumentCreateSerializer(serializers.ModelSerializer):
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
        )
        read_only_fields = ("id",)

    def validate_dossier(self, value):
        if value.is_archived:
            raise serializers.ValidationError("Cannot add documents to an archived dossier.")
        return value

    def create(self, validated_data):
        user = self.context["request"].user
        validated_data["created_by"] = user
        document = super().create(validated_data)
        AuditLog.objects.create(
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
        AuditLog.objects.create(
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

class DossierListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dossier
        fields = (
            "id",
            "file_number",
            "full_name",
            "national_id",
            "personal_id",
            "governorate",
            "room_number",
            "column_number",
            "shelf_number",
            "created_by",
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
    file_path = serializers.CharField(max_length=500)
    file_size_kb = serializers.IntegerField(min_value=Document.MIN_FILE_SIZE_KB, max_value=Document.MAX_FILE_SIZE_KB)
    mime_type = serializers.CharField(max_length=50)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)

    def validate_mime_type(self, value: str) -> str:
        if value != Document.PDF_MIME_TYPE:
            raise serializers.ValidationError("Only PDF uploads are allowed.")
        return value

    def validate_file_path(self, value: str) -> str:
        if not value.lower().endswith(".pdf"):
            raise serializers.ValidationError("File path must point to a .pdf file.")
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

