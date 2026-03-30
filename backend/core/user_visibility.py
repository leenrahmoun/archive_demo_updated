from django.contrib.auth import get_user_model
from django.db.models import Q


User = get_user_model()


def get_operational_user_queryset():
    return User.objects.filter(is_superuser=False)


def exclude_emergency_only_users(queryset):
    return queryset.exclude(is_superuser=True)


def exclude_emergency_only_audit_logs(queryset):
    emergency_user_ids = User.objects.filter(is_superuser=True).values_list("id", flat=True)
    return queryset.exclude(Q(user__is_superuser=True) | Q(entity_type="user", entity_id__in=emergency_user_ids))
