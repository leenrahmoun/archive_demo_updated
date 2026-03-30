"""Management command to seed lookup data: governorates and document types."""

from django.core.management.base import BaseCommand

from core.reference_data import sync_core_document_types, sync_core_governorates


class Command(BaseCommand):
    help = "Seed governorates and document types lookup tables. Idempotent – safe to run multiple times."

    def handle(self, *args, **options):
        self._seed_governorates()
        self._seed_document_types()
        self.stdout.write(self.style.SUCCESS("Lookup seeding complete."))

    def _seed_governorates(self):
        result = sync_core_governorates()
        self.stdout.write(
            f"  Governorates: {result['created']} created, {result['updated']} already existed (is_active ensured)."
        )

    def _seed_document_types(self):
        result = sync_core_document_types()
        self.stdout.write(
            f"  Document types: {result['created']} created, {result['updated']} already existed (ensured current values)."
        )
