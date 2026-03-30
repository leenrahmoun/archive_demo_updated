from core.reference_data import sync_core_document_types


def bootstrap_core_document_types(sender, using, **kwargs):
    sync_core_document_types(using=using)
