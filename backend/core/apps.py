from django.apps import AppConfig
from django.db.models.signals import post_migrate


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        from core.signals import bootstrap_core_document_types

        post_migrate.connect(
            bootstrap_core_document_types,
            sender=self,
            dispatch_uid="core.bootstrap_core_document_types",
        )
