import re


NUMERIC_ONLY_MESSAGE = "هذا الحقل يجب أن يحتوي على أرقام فقط."
SYRIAN_NATIONAL_ID_MESSAGE = "الرقم الوطني للسوري يجب أن يتكون من 10 أو 11 رقمًا."
NON_SYRIAN_NATIONALITY_REQUIRED_MESSAGE = "يرجى إدخال الجنسية أو البلد عندما تكون الجنسية غير سورية."

NUMERIC_ONLY_DOSSIER_FIELDS = (
    "national_id",
    "personal_id",
    "room_number",
    "column_number",
    "shelf_number",
)


def normalize_text_value(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def validate_dossier_identity_data(
    *,
    is_non_syrian,
    nationality_name,
    national_id,
    personal_id,
    room_number,
    column_number,
    shelf_number,
):
    normalized_values = {
        "national_id": normalize_text_value(national_id),
        "personal_id": normalize_text_value(personal_id),
        "room_number": normalize_text_value(room_number),
        "column_number": normalize_text_value(column_number),
        "shelf_number": normalize_text_value(shelf_number),
    }
    normalized_nationality_name = normalize_text_value(nationality_name)
    errors = {}

    for field_name, value in normalized_values.items():
        if value and not value.isdigit():
            errors[field_name] = NUMERIC_ONLY_MESSAGE

    national_id_value = normalized_values["national_id"]
    if is_non_syrian:
        if not normalized_nationality_name:
            errors["nationality_name"] = NON_SYRIAN_NATIONALITY_REQUIRED_MESSAGE
    else:
        normalized_nationality_name = ""
        if national_id_value and national_id_value.isdigit() and len(national_id_value) not in (10, 11):
            errors["national_id"] = SYRIAN_NATIONAL_ID_MESSAGE

    return {
        "normalized_values": normalized_values,
        "normalized_nationality_name": normalized_nationality_name,
        "errors": errors,
    }
