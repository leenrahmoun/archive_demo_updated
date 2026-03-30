import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { DocumentTypeAutocomplete } from "../components/DocumentTypeAutocomplete";
import { createDossier } from "../api/dossiersApi";
import { getDocumentTypes, getGovernorates } from "../api/lookupsApi";
import { flattenErrors } from "../utils/errors";

const MIN_FILE_SIZE_KB = 100;
const MAX_FILE_SIZE_KB = 15360;
const SYRIAN_NATIONAL_ID_ERROR_MESSAGE = "الرقم الوطني للسوري يجب أن يتكون من 10 أو 11 رقمًا.";
const NON_SYRIAN_NATIONALITY_ERROR_MESSAGE = "يرجى إدخال الجنسية أو البلد عندما تكون الجنسية غير سورية.";

function initialFormState() {
  return {
    file_number: "",
    full_name: "",
    national_id: "",
    personal_id: "",
    is_non_syrian: false,
    nationality_name: "",
    governorate_id: "",
    room_number: "",
    column_number: "",
    shelf_number: "",
    doc_type_id: "",
    doc_number: "",
    doc_name: "",
    notes: "",
  };
}

function normalizeText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function digitsOnly(value) {
  return String(value || "").replace(/\D+/g, "");
}

function isSyrianNationalIdValid(value) {
  return /^\d{10,11}$/.test(value);
}

function extractFirstErrorMessage(node) {
  if (!node) {
    return "";
  }
  if (typeof node === "string") {
    return node;
  }
  if (Array.isArray(node)) {
    for (const item of node) {
      const message = extractFirstErrorMessage(item);
      if (message) {
        return message;
      }
    }
    return "";
  }
  if (typeof node === "object") {
    for (const value of Object.values(node)) {
      const message = extractFirstErrorMessage(value);
      if (message) {
        return message;
      }
    }
  }
  return "";
}

function parseCreateDossierErrors(payload) {
  const fieldErrors = {};
  const generalErrors = [];

  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    const fallbackMessage = extractFirstErrorMessage(payload);
    return {
      fieldErrors,
      generalErrors: fallbackMessage ? [fallbackMessage] : [],
    };
  }

  const assignFieldError = (fieldName, node) => {
    const message = extractFirstErrorMessage(node);
    if (message) {
      fieldErrors[fieldName] = message;
    }
  };

  assignFieldError("file_number", payload.file_number);
  assignFieldError("full_name", payload.full_name);
  assignFieldError("national_id", payload.national_id);
  assignFieldError("personal_id", payload.personal_id);
  assignFieldError("nationality_name", payload.nationality_name);
  assignFieldError("governorate_id", payload.governorate_id);
  assignFieldError("room_number", payload.room_number);
  assignFieldError("column_number", payload.column_number);
  assignFieldError("shelf_number", payload.shelf_number);

  if (payload.first_document && typeof payload.first_document === "object" && !Array.isArray(payload.first_document)) {
    assignFieldError("doc_type_id", payload.first_document.doc_type_id);
    assignFieldError("file", payload.first_document.file);

    const firstDocumentGeneralError = extractFirstErrorMessage(payload.first_document.non_field_errors || payload.first_document.detail);
    if (firstDocumentGeneralError) {
      generalErrors.push(firstDocumentGeneralError);
    }
  } else if (payload.first_document) {
    const firstDocumentMessage = extractFirstErrorMessage(payload.first_document);
    if (firstDocumentMessage) {
      generalErrors.push(firstDocumentMessage);
    }
  }

  const detailMessage = extractFirstErrorMessage(payload.detail);
  if (detailMessage) {
    generalErrors.push(detailMessage);
  }

  const nonFieldMessage = extractFirstErrorMessage(payload.non_field_errors);
  if (nonFieldMessage) {
    generalErrors.push(nonFieldMessage);
  }

  if (!generalErrors.length && !Object.keys(fieldErrors).length) {
    return {
      fieldErrors,
      generalErrors: flattenErrors(payload),
    };
  }

  return {
    fieldErrors,
    generalErrors: Array.from(new Set(generalErrors.filter(Boolean))),
  };
}

export function CreateDossierPage() {
  const navigate = useNavigate();
  const [governorates, setGovernorates] = useState([]);
  const [documentTypes, setDocumentTypes] = useState([]);
  const [form, setForm] = useState(initialFormState);
  const [selectedFile, setSelectedFile] = useState(null);
  const [generalErrors, setGeneralErrors] = useState([]);
  const [fieldErrors, setFieldErrors] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    let isActive = true;

    async function loadDocumentTypes() {
      try {
        const response = await getDocumentTypes();
        if (isActive) {
          setDocumentTypes(Array.isArray(response) ? response : []);
        }
      } catch {
        if (isActive) {
          setDocumentTypes([]);
        }
      }
    }

    getGovernorates().then(setGovernorates).catch(() => setGovernorates([]));
    loadDocumentTypes();
    window.addEventListener("focus", loadDocumentTypes);

    return () => {
      isActive = false;
      window.removeEventListener("focus", loadDocumentTypes);
    };
  }, []);

  const fileSizeKb = useMemo(() => {
    if (!selectedFile) {
      return null;
    }
    return Math.ceil(selectedFile.size / 1024);
  }, [selectedFile]);

  function clearFieldError(fieldName) {
    setFieldErrors((previous) => {
      if (!previous[fieldName]) {
        return previous;
      }
      const next = { ...previous };
      delete next[fieldName];
      return next;
    });
  }

  function updateField(fieldName, value) {
    setGeneralErrors([]);
    clearFieldError(fieldName);
    setForm((previous) => ({ ...previous, [fieldName]: value }));
  }

  function updateNumericField(fieldName, value) {
    updateField(fieldName, digitsOnly(value));
  }

  function onNationalityModeChange(event) {
    const checked = event.target.checked;
    setGeneralErrors([]);
    clearFieldError("nationality_name");
    clearFieldError("governorate_id");
    setForm((previous) => ({
      ...previous,
      is_non_syrian: checked,
      nationality_name: checked ? previous.nationality_name : "",
      governorate_id: checked ? "" : previous.governorate_id,
    }));
  }

  function onFileChange(event) {
    setGeneralErrors([]);
    clearFieldError("file");
    const file = event.target.files?.[0] || null;
    setSelectedFile(file);
  }

  function validateForm() {
    const nextFieldErrors = {};

    if (!form.doc_type_id) {
      nextFieldErrors.doc_type_id = "يرجى اختيار نوع الوثيقة من القائمة المقترحة.";
    }

    if (!form.is_non_syrian && !isSyrianNationalIdValid(form.national_id)) {
      nextFieldErrors.national_id = SYRIAN_NATIONAL_ID_ERROR_MESSAGE;
    }

    if (form.is_non_syrian && !normalizeText(form.nationality_name)) {
      nextFieldErrors.nationality_name = NON_SYRIAN_NATIONALITY_ERROR_MESSAGE;
    }

    if (!selectedFile) {
      nextFieldErrors.file = "يجب اختيار ملف PDF للوثيقة الأولى.";
    } else if (selectedFile.type !== "application/pdf") {
      nextFieldErrors.file = "نوع الملف غير مدعوم. يجب أن يكون PDF فقط.";
    } else if (fileSizeKb < MIN_FILE_SIZE_KB || fileSizeKb > MAX_FILE_SIZE_KB) {
      nextFieldErrors.file = `حجم الملف يجب أن يكون بين ${MIN_FILE_SIZE_KB}KB و ${MAX_FILE_SIZE_KB}KB.`;
    }

    return nextFieldErrors;
  }

  async function onSubmit(event) {
    event.preventDefault();
    setGeneralErrors([]);

    const nextFieldErrors = validateForm();
    setFieldErrors(nextFieldErrors);
    if (Object.keys(nextFieldErrors).length) {
      return;
    }

    const payload = new FormData();
    payload.append("file_number", normalizeText(form.file_number));
    payload.append("full_name", normalizeText(form.full_name));
    payload.append("national_id", form.national_id);
    payload.append("personal_id", form.personal_id);
    payload.append("is_non_syrian", String(form.is_non_syrian));
    payload.append("nationality_name", form.is_non_syrian ? normalizeText(form.nationality_name) : "");
    if (!form.is_non_syrian && form.governorate_id) {
      payload.append("governorate_id", form.governorate_id);
    }
    payload.append("room_number", form.room_number);
    payload.append("column_number", form.column_number);
    payload.append("shelf_number", form.shelf_number);
    payload.append("first_document.doc_type_id", form.doc_type_id);
    payload.append("first_document.doc_number", normalizeText(form.doc_number));
    payload.append("first_document.doc_name", normalizeText(form.doc_name));
    payload.append("first_document.notes", form.notes || "");
    payload.append("first_document.file", selectedFile);

    setIsSubmitting(true);
    try {
      const created = await createDossier(payload);
      const firstCreatedDocument = created.documents?.[0];

      if (firstCreatedDocument?.id) {
        navigate(`/documents/${firstCreatedDocument.id}`, {
          state: {
            successMessage: "تم إنشاء الإضبارة والوثيقة الأولى بنجاح. يمكنك الآن إرسال الوثيقة للمراجعة.",
            fromDossierCreation: true,
          },
        });
        return;
      }

      navigate(`/dossiers/${created.id}`);
    } catch (err) {
      const parsedErrors = parseCreateDossierErrors(err?.response?.data);
      setFieldErrors(parsedErrors.fieldErrors);
      setGeneralErrors(parsedErrors.generalErrors.length ? parsedErrors.generalErrors : ["فشل إنشاء الإضبارة."]);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section>
      <h2>إنشاء إضبارة مع الوثيقة الأولى</h2>
      <form className="card form-grid" onSubmit={onSubmit}>
        <h3 className="full-row">بيانات الإضبارة</h3>

        <label className="form-field">
          <span>رقم الملف</span>
          <input
            placeholder="رقم الملف"
            value={form.file_number}
            onChange={(event) => updateField("file_number", event.target.value)}
            required
          />
          {fieldErrors.file_number ? <small className="form-field__error">{fieldErrors.file_number}</small> : null}
        </label>

        <label className="form-field">
          <span>الاسم الكامل</span>
          <input
            placeholder="الاسم الكامل"
            value={form.full_name}
            onChange={(event) => updateField("full_name", event.target.value)}
            required
          />
          {fieldErrors.full_name ? <small className="form-field__error">{fieldErrors.full_name}</small> : null}
        </label>

        <label className="form-field">
          <span>الرقم الوطني</span>
          <input
            type="text"
            inputMode="numeric"
            pattern="\d*"
            maxLength={form.is_non_syrian ? 30 : 11}
            placeholder="الرقم الوطني"
            value={form.national_id}
            onChange={(event) => updateNumericField("national_id", event.target.value)}
            required
          />
          {fieldErrors.national_id ? <small className="form-field__error">{fieldErrors.national_id}</small> : null}
        </label>

        <label className="form-field">
          <span>الرقم الذاتي</span>
          <input
            type="text"
            inputMode="numeric"
            pattern="\d*"
            maxLength={30}
            placeholder="الرقم الذاتي"
            value={form.personal_id}
            onChange={(event) => updateNumericField("personal_id", event.target.value)}
            required
          />
          {fieldErrors.personal_id ? <small className="form-field__error">{fieldErrors.personal_id}</small> : null}
        </label>

        <div className="full-row dossier-nationality-toggle">
          <label className="checkbox-row">
            <input type="checkbox" checked={form.is_non_syrian} onChange={onNationalityModeChange} />
            <span>هل الجنسية غير سورية؟</span>
          </label>
        </div>

        {form.is_non_syrian ? (
          <label className="form-field">
            <span>الجنسية أو البلد</span>
            <input
              placeholder="أدخل الجنسية أو اسم البلد"
              value={form.nationality_name}
              onChange={(event) => updateField("nationality_name", event.target.value)}
              required={form.is_non_syrian}
            />
            {fieldErrors.nationality_name ? <small className="form-field__error">{fieldErrors.nationality_name}</small> : null}
          </label>
        ) : (
          <label className="form-field">
            <span>المحافظة</span>
            <select value={form.governorate_id} onChange={(event) => updateField("governorate_id", event.target.value)}>
              <option value="">بدون محافظة</option>
              {governorates.map((gov) => (
                <option value={gov.id} key={gov.id}>
                  {gov.name}
                </option>
              ))}
            </select>
            {fieldErrors.governorate_id ? <small className="form-field__error">{fieldErrors.governorate_id}</small> : null}
          </label>
        )}

        <label className="form-field">
          <span>رقم الغرفة</span>
          <input
            type="text"
            inputMode="numeric"
            pattern="\d*"
            placeholder="رقم الغرفة"
            value={form.room_number}
            onChange={(event) => updateNumericField("room_number", event.target.value)}
            required
          />
          {fieldErrors.room_number ? <small className="form-field__error">{fieldErrors.room_number}</small> : null}
        </label>

        <label className="form-field">
          <span>رقم العمود</span>
          <input
            type="text"
            inputMode="numeric"
            pattern="\d*"
            placeholder="رقم العمود"
            value={form.column_number}
            onChange={(event) => updateNumericField("column_number", event.target.value)}
            required
          />
          {fieldErrors.column_number ? <small className="form-field__error">{fieldErrors.column_number}</small> : null}
        </label>

        <label className="form-field">
          <span>رقم الرف</span>
          <input
            type="text"
            inputMode="numeric"
            pattern="\d*"
            placeholder="رقم الرف"
            value={form.shelf_number}
            onChange={(event) => updateNumericField("shelf_number", event.target.value)}
            required
          />
          {fieldErrors.shelf_number ? <small className="form-field__error">{fieldErrors.shelf_number}</small> : null}
        </label>

        <h3 className="full-row">بيانات الوثيقة الأولى</h3>

        <DocumentTypeAutocomplete
          options={documentTypes}
          value={form.doc_type_id}
          onChange={(nextValue) => {
            setGeneralErrors([]);
            clearFieldError("doc_type_id");
            setForm((prev) => ({ ...prev, doc_type_id: nextValue }));
          }}
          helperText=""
          errorText={fieldErrors.doc_type_id}
          required
        />

        <label className="form-field">
          <span>رقم الوثيقة</span>
          <input
            placeholder="رقم الوثيقة"
            value={form.doc_number}
            onChange={(event) => updateField("doc_number", event.target.value)}
            required
          />
        </label>

        <label className="form-field">
          <span>اسم الوثيقة</span>
          <input
            placeholder="اسم الوثيقة"
            value={form.doc_name}
            onChange={(event) => updateField("doc_name", event.target.value)}
            required
          />
        </label>

        <label className="form-field">
          <span>ملاحظات</span>
          <input
            placeholder="ملاحظات (اختياري)"
            value={form.notes}
            onChange={(event) => updateField("notes", event.target.value)}
          />
        </label>

        <label className="form-field full-row">
          <span>ملف الوثيقة الأولى</span>
          <input type="file" accept="application/pdf,.pdf" onChange={onFileChange} required />
          {fieldErrors.file ? <small className="form-field__error">{fieldErrors.file}</small> : null}
        </label>

        {generalErrors.length ? (
          <ul className="error-list full-row">
            {generalErrors.map((message, index) => (
              <li key={`${message}-${index}`}>{message}</li>
            ))}
          </ul>
        ) : null}

        <button type="submit" className="full-row" disabled={isSubmitting}>
          {isSubmitting ? "جاري الحفظ..." : "إنشاء الإضبارة"}
        </button>
      </form>
    </section>
  );
}
