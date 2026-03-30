from core.reference_data import sync_core_document_types, sync_core_governorates


def bootstrap_core_reference_data(sender, using, **kwargs):
    sync_core_governorates(using=using)
    sync_core_document_types(using=using)
