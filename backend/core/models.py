from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class UserRole(models.TextChoices):
    ADMIN = "admin", "Admin"
    DATA_ENTRY = "data_entry", "Data Entry"
    AUDITOR = "auditor", "Auditor"
    READER = "reader", "Reader"


class User(AbstractUser):
    role = models.CharField(max_length=20, choices=UserRole.choices)
    assigned_auditor = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="assigned_data_entries",
        null=True,
        blank=True,
        limit_choices_to={"role": UserRole.AUDITOR},
    )

    def clean(self) -> None:
        super().clean()
        if self.assigned_auditor is None:
            return
        if self.role != UserRole.DATA_ENTRY:
            raise ValidationError({"assigned_auditor": "Only Data Entry users can have an assigned auditor."})
        if self.assigned_auditor.role != UserRole.AUDITOR:
            raise ValidationError({"assigned_auditor": "Assigned reviewer must have the auditor role."})

    def __str__(self) -> str:
        return f"{self.username} ({self.role})"


class Governorate(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class DocumentType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    group_name = models.CharField(max_length=100)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("group_name", "display_order", "name", "id")

    def __str__(self) -> str:
        return self.name


class Dossier(models.Model):
    file_number = models.CharField(max_length=50, unique=True)
    full_name = models.CharField(max_length=200)
    national_id = models.CharField(max_length=30, unique=True)
    personal_id = models.CharField(max_length=30)
    governorate = models.ForeignKey(
        Governorate, on_delete=models.PROTECT, related_name="dossiers", null=True, blank=True
    )
    room_number = models.CharField(max_length=20)
    column_number = models.CharField(max_length=20)
    shelf_number = models.CharField(max_length=20)
    created_by = models.ForeignKey("User", on_delete=models.PROTECT, related_name="created_dossiers")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_archived = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["national_id"]),
            models.Index(fields=["personal_id"]),
            models.Index(fields=["file_number"]),
        ]

    def __str__(self) -> str:
        return self.file_number


class DocumentStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class Document(models.Model):
    MIN_FILE_SIZE_KB = 100
    MAX_FILE_SIZE_KB = 15 * 1024
    PDF_MIME_TYPE = "application/pdf"

    dossier = models.ForeignKey(Dossier, on_delete=models.PROTECT, related_name="documents")
    doc_type = models.ForeignKey(DocumentType, on_delete=models.PROTECT, related_name="documents")
    doc_number = models.CharField(max_length=100)
    doc_name = models.CharField(max_length=200)
    file_path = models.CharField(max_length=500, unique=True)
    file_size_kb = models.PositiveIntegerField()
    mime_type = models.CharField(max_length=50, default=PDF_MIME_TYPE)
    status = models.CharField(
        max_length=20,
        choices=DocumentStatus.choices,
        default=DocumentStatus.DRAFT,
    )
    notes = models.CharField(max_length=500, null=True, blank=True)
    created_by = models.ForeignKey("User", on_delete=models.PROTECT, related_name="created_documents")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "User",
        on_delete=models.PROTECT,
        related_name="reviewed_documents",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        "User",
        on_delete=models.PROTECT,
        related_name="deleted_documents",
        null=True,
        blank=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=["dossier"]),
            models.Index(fields=["status"]),
            models.Index(fields=["doc_number"]),
            models.Index(fields=["dossier", "is_deleted"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(file_size_kb__gte=100),
                name="document_file_size_min_100kb",
            ),
            models.CheckConstraint(
                check=Q(file_size_kb__lte=15360),
                name="document_file_size_max_15mb",
            ),
            models.UniqueConstraint(
                fields=["dossier", "doc_type", "doc_number"],
                condition=Q(is_deleted=False),
                name="unique_active_document_per_dossier_type_number",
            ),
        ]

    def clean(self) -> None:
        if self.mime_type != self.PDF_MIME_TYPE:
            raise ValidationError({"mime_type": "Only PDF uploads are allowed."})
        if not self.file_path.lower().endswith(".pdf"):
            raise ValidationError({"file_path": "File path must point to a .pdf file."})
        if self.file_size_kb < self.MIN_FILE_SIZE_KB or self.file_size_kb > self.MAX_FILE_SIZE_KB:
            raise ValidationError(
                {"file_size_kb": f"File size must be between {self.MIN_FILE_SIZE_KB}KB and {self.MAX_FILE_SIZE_KB}KB."}
            )
        if self.status == DocumentStatus.REJECTED and not self.rejection_reason:
            raise ValidationError({"rejection_reason": "Rejection reason is required when status is rejected."})

    def __str__(self) -> str:
        return f"{self.doc_number} - {self.status}"


class AuditAction(models.TextChoices):
    CREATE = "create", "Create"
    UPDATE = "update", "Update"
    SUBMIT = "submit", "Submit"
    APPROVE = "approve", "Approve"
    REJECT = "reject", "Reject"
    REPLACE_FILE = "replace_file", "Replace File"
    DELETE = "delete", "Delete"
    RESTORE = "restore", "Restore"


class AuditLog(models.Model):
    user = models.ForeignKey("User", on_delete=models.PROTECT, related_name="audit_logs")
    action = models.CharField(max_length=50, choices=AuditAction.choices)
    entity_type = models.CharField(max_length=50)
    entity_id = models.BigIntegerField()
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["entity_type", "entity_id"])]

    def __str__(self) -> str:
        return f"{self.action} {self.entity_type}:{self.entity_id}"
