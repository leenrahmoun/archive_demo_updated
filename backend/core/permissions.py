from rest_framework.permissions import SAFE_METHODS, BasePermission

from core.models import UserRole


class DossierPermission(BasePermission):
    """
    MVP role policy:
    - admin: full access
    - data_entry: create and read
    - auditor: read only
    - reader: read only
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role == UserRole.ADMIN:
            return True
        if request.method in SAFE_METHODS:
            return user.role in {UserRole.DATA_ENTRY, UserRole.AUDITOR, UserRole.READER}
        if request.method == "POST":
            return user.role == UserRole.DATA_ENTRY
        return False


class DocumentPermission(BasePermission):
    """
    MVP role policy:
    - admin: full access
    - data_entry: create, read, update
    - auditor: read only
    - reader: read only
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role == UserRole.ADMIN:
            return True
        if request.method in SAFE_METHODS:
            return user.role in {UserRole.DATA_ENTRY, UserRole.AUDITOR, UserRole.READER}
        if request.method in ["POST", "PUT", "PATCH"]:
            return user.role == UserRole.DATA_ENTRY
        return False


class DocumentWorkflowPermission(BasePermission):
    """
    Endpoint-level workflow permissions.
    View must expose `workflow_action` in: submit, approve, reject, soft_delete.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role == UserRole.ADMIN:
            return True

        action = getattr(view, "workflow_action", "")
        if action == "submit":
            return user.role == UserRole.DATA_ENTRY
        if action in {"approve", "reject"}:
            return user.role == UserRole.AUDITOR
        if action == "soft_delete":
            return user.role == UserRole.DATA_ENTRY
        return False


class AuditLogPermission(BasePermission):
    """Read-only audit log access for admin only."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method not in SAFE_METHODS:
            return False
        return user.role == UserRole.ADMIN


class AdminOnlyPermission(BasePermission):
    """Full access for admin users only."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return user.role == UserRole.ADMIN

