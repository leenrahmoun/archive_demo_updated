import json
from functools import lru_cache
from pathlib import Path


DOCUMENT_TYPES_DATA_FILE = (
    Path(__file__).resolve().parent / "management" / "commands" / "data" / "document_types.json"
)


@lru_cache(maxsize=1)
def get_approved_document_type_entries():
    return tuple(json.loads(DOCUMENT_TYPES_DATA_FILE.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def get_approved_document_type_slugs():
    return tuple(entry["slug"] for entry in get_approved_document_type_entries())
