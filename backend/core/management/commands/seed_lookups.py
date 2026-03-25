"""Management command to seed lookup data: governorates and document types."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from core.models import DocumentType, Governorate

DATA_DIR = Path(__file__).parent / "data"


class Command(BaseCommand):
    help = "Seed governorates and document types lookup tables. Idempotent – safe to run multiple times."

    def handle(self, *args, **options):
        self._seed_governorates()
        self._seed_document_types()
        self.stdout.write(self.style.SUCCESS("Lookup seeding complete."))

    def _seed_governorates(self):
        data = json.loads((DATA_DIR / "governorates.json").read_text(encoding="utf-8"))
        created = updated = 0
        for entry in data:
            obj, is_new = Governorate.objects.update_or_create(
                name=entry["name"],
                defaults={"is_active": True},
            )
            if is_new:
                created += 1
            else:
                updated += 1
        self.stdout.write(
            f"  Governorates: {created} created, {updated} already existed (is_active ensured)."
        )

    def _seed_document_types(self):
        data = json.loads((DATA_DIR / "document_types.json").read_text(encoding="utf-8"))
        created = updated = 0
        for entry in data:
            obj, is_new = DocumentType.objects.update_or_create(
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
        self.stdout.write(
            f"  Document types: {created} created, {updated} already existed (ensured current values)."
        )
