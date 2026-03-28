from datetime import date, datetime, time
from enum import Enum

from core.models import AuditLog


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
