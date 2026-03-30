import json
from pathlib import Path

from django.db import DEFAULT_DB_ALIAS, transaction

from core.models import DocumentType, Governorate

DATA_DIR = Path(__file__).resolve().parent / "management" / "commands" / "data"


def get_core_governorate_entries():
    return json.loads((DATA_DIR / "governorates.json").read_text(encoding="utf-8"))


def get_core_document_type_entries():
    return json.loads((DATA_DIR / "document_types.json").read_text(encoding="utf-8"))


def sync_core_governorates(*, using=DEFAULT_DB_ALIAS):
    entries = get_core_governorate_entries()
    manager = Governorate.objects.using(using)
    created = 0
    updated = 0

    with transaction.atomic(using=using):
        for entry in entries:
            _, is_new = manager.update_or_create(
                name=entry["name"],
                defaults={
                    "is_active": True,
                },
            )
            if is_new:
                created += 1
            else:
                updated += 1

    return {
        "created": created,
        "updated": updated,
        "total": len(entries),
    }


def sync_core_document_types(*, using=DEFAULT_DB_ALIAS):
    entries = get_core_document_type_entries()
    manager = DocumentType.objects.using(using)
    created = 0
    updated = 0

    with transaction.atomic(using=using):
        for entry in entries:
            _, is_new = manager.update_or_create(
                slug=entry["slug"],
                defaults={
                    "name": entry["name"],
                    "group_name": entry["group"],
                    "display_order": entry["order"],
                    "is_active": True,
                },
            )
            if is_new:
                created += 1
            else:
                updated += 1

    return {
        "created": created,
        "updated": updated,
        "total": len(entries),
    }
