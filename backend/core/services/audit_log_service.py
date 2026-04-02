from datetime import date, datetime, time
from enum import Enum

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from core.models import AuditAction, AuditLog, Document


User = get_user_model()


def json_safe_value(value):
    if isinstance(value, dict):
        return {key: json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe_value(item) for item in value]
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def json_safe_dict(values):
    if values is None:
        return None
    return {key: json_safe_value(value) for key, value in values.items()}


def create_audit_log(*, user, action, entity_type, entity_id, old_values=None, new_values=None, ip_address=None):
    return AuditLog.objects.create(
        user=user,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=json_safe_dict(old_values),
        new_values=json_safe_dict(new_values),
        ip_address=ip_address,
    )


def get_request_ip_address(request):
    if request is None:
        return None

    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or None

    return request.META.get("REMOTE_ADDR")


def log_user_security_event(*, user, action, request=None, message, reason=None):
    if user is None:
        return None

    new_values = {
        "message": message,
        "username": user.username,
    }
    if reason:
        new_values["reason"] = reason

    return create_audit_log(
        user=user,
        action=action,
        entity_type="user",
        entity_id=user.id,
        old_values=None,
        new_values=new_values,
        ip_address=get_request_ip_address(request),
    )


def resolve_user_from_refresh_token(refresh_token):
    if not refresh_token:
        return None

    outstanding_token = OutstandingToken.objects.select_related("user").filter(token=refresh_token).first()
    if outstanding_token is not None:
        return outstanding_token.user

    try:
        token = RefreshToken(refresh_token)
    except TokenError:
        return None

    user_id = token.payload.get("user_id")
    if user_id is None:
        return None

    return User.objects.filter(id=user_id).first()


def log_document_workflow_access_denied(*, user, workflow_action, request=None, reason, document=None, document_id=None):
    if user is None or not getattr(user, "is_authenticated", False):
        return None

    resolved_document = document
    if resolved_document is None and document_id is not None:
        resolved_document = Document.objects.filter(pk=document_id).first()

    entity_id = resolved_document.id if resolved_document is not None else int(document_id or 0)
    old_values = None
    if resolved_document is not None:
        old_values = {
            "status": resolved_document.status,
            "is_deleted": resolved_document.is_deleted,
            "doc_number": resolved_document.doc_number,
        }

    return create_audit_log(
        user=user,
        action=AuditAction.ACCESS_DENIED,
        entity_type="document",
        entity_id=entity_id,
        old_values=old_values,
        new_values={
            "message": f"Denied {workflow_action} attempt.",
            "workflow_action": workflow_action,
            "reason": reason,
        },
        ip_address=get_request_ip_address(request),
    )
