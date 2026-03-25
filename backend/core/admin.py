from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import AuditLog, Document, DocumentType, Dossier, Governorate, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (("Role", {"fields": ("role",)}),)
    list_display = ("username", "email", "role", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff")


@admin.register(Governorate)
class GovernorateAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active",)


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "group_name", "display_order", "is_active")
    search_fields = ("name", "slug", "group_name")
    list_filter = ("is_active", "group_name")
    ordering = ("group_name", "display_order", "id")


@admin.register(Dossier)
class DossierAdmin(admin.ModelAdmin):
    list_display = ("id", "file_number", "full_name", "national_id", "created_by", "is_archived")
    search_fields = ("file_number", "full_name", "national_id", "personal_id")
    list_filter = ("is_archived",)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "doc_number", "doc_name", "status", "dossier", "is_deleted")
    search_fields = ("doc_number", "doc_name", "file_path")
    list_filter = ("status", "is_deleted", "mime_type")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "action", "entity_type", "entity_id", "created_at")
    search_fields = ("entity_type", "entity_id", "user__username")
    list_filter = ("action", "entity_type")
