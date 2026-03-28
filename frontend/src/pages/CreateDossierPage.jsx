import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { DocumentTypeAutocomplete } from "../components/DocumentTypeAutocomplete";
import { createDossier } from "../api/dossiersApi";
import { getDocumentTypes, getGovernorates } from "../api/lookupsApi";
import { flattenErrors } from "../utils/errors";

const MIN_FILE_SIZE_KB = 100;
const MAX_FILE_SIZE_KB = 15360;

function initialFormState() {
  return {
    file_number: "",
    full_name: "",
    national_id: "",
    personal_id: "",
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

export function CreateDossierPage() {
  const navigate = useNavigate();
  const [governorates, setGovernorates] = useState([]);
  const [documentTypes, setDocumentTypes] = useState([]);
  const [form, setForm] = useState(initialFormState);
  const [selectedFile, setSelectedFile] = useState(null);
  const [errors, setErrors] = useState([]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    getGovernorates().then(setGovernorates).catch(() => setGovernorates([]));
    getDocumentTypes().then(setDocumentTypes).catch(() => setDocumentTypes([]));
  }, []);

  const fileSizeKb = useMemo(() => {
    if (!selectedFile) {
      return null;
    }
    return Math.ceil(selectedFile.size / 1024);
  }, [selectedFile]);

  function onFileChange(event) {
    const file = event.target.files?.[0] || null;
    setSelectedFile(file);
  }

  async function onSubmit(event) {
    event.preventDefault();
    setErrors([]);

    if (!form.doc_type_id) {
      setErrors(["يرجى اختيار نوع الوثيقة من القائمة المقترحة."]);
      return;
    }

    if (!selectedFile) {
      setErrors(["يجب اختيار ملف PDF للوثيقة الأولى."]);
      return;
    }
    if (selectedFile.type !== "application/pdf") {
      setErrors(["نوع الملف غير مدعوم. يجب أن يكون PDF فقط."]);
      return;
    }
    if (fileSizeKb < MIN_FILE_SIZE_KB || fileSizeKb > MAX_FILE_SIZE_KB) {
      setErrors([`حجم الملف يجب أن يكون بين ${MIN_FILE_SIZE_KB}KB و ${MAX_FILE_SIZE_KB}KB.`]);
      return;
    }

    const payload = new FormData();
    payload.append("file_number", form.file_number);
    payload.append("full_name", form.full_name);
    payload.append("national_id", form.national_id);
    payload.append("personal_id", form.personal_id);
    if (form.governorate_id) {
      payload.append("governorate_id", form.governorate_id);
    }
    payload.append("room_number", form.room_number);
    payload.append("column_number", form.column_number);
    payload.append("shelf_number", form.shelf_number);
    payload.append("first_document.doc_type_id", form.doc_type_id);
    payload.append("first_document.doc_number", form.doc_number);
    payload.append("first_document.doc_name", form.doc_name);
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
      const backendErrors = flattenErrors(err?.response?.data);
      setErrors(backendErrors.length ? backendErrors : ["فشل إنشاء الإضبارة."]);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section>
      <h2>إنشاء إضبارة مع الوثيقة الأولى</h2>
      <form className="card form-grid" onSubmit={onSubmit}>
        <input placeholder="رقم الملف" value={form.file_number} onChange={(e) => setForm((p) => ({ ...p, file_number: e.target.value }))} required />
        <input placeholder="الاسم الكامل" value={form.full_name} onChange={(e) => setForm((p) => ({ ...p, full_name: e.target.value }))} required />
        <input placeholder="الرقم الوطني" value={form.national_id} onChange={(e) => setForm((p) => ({ ...p, national_id: e.target.value }))} required />
        <input placeholder="الرقم الشخصي" value={form.personal_id} onChange={(e) => setForm((p) => ({ ...p, personal_id: e.target.value }))} required />
        <select value={form.governorate_id} onChange={(e) => setForm((p) => ({ ...p, governorate_id: e.target.value }))}>
          <option value="">بدون محافظة</option>
          {governorates.map((gov) => (
            <option value={gov.id} key={gov.id}>
              {gov.name}
            </option>
          ))}
        </select>
        <input placeholder="رقم الغرفة" value={form.room_number} onChange={(e) => setForm((p) => ({ ...p, room_number: e.target.value }))} required />
        <input placeholder="رقم العمود" value={form.column_number} onChange={(e) => setForm((p) => ({ ...p, column_number: e.target.value }))} required />
        <input placeholder="رقم الرف" value={form.shelf_number} onChange={(e) => setForm((p) => ({ ...p, shelf_number: e.target.value }))} required />

        <h3 className="full-row">بيانات الوثيقة الأولى</h3>
        <DocumentTypeAutocomplete
          options={documentTypes}
          value={form.doc_type_id}
          onChange={(nextValue) => {
            setErrors([]);
            setForm((prev) => ({ ...prev, doc_type_id: nextValue }));
          }}
          required
        />
        <input placeholder="رقم الوثيقة" value={form.doc_number} onChange={(e) => setForm((p) => ({ ...p, doc_number: e.target.value }))} required />
        <input placeholder="اسم الوثيقة" value={form.doc_name} onChange={(e) => setForm((p) => ({ ...p, doc_name: e.target.value }))} required />
        <input placeholder="ملاحظات (اختياري)" value={form.notes} onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))} />
        <input type="file" accept="application/pdf,.pdf" onChange={onFileChange} required />
        <p className="muted full-row">يسمح بملف PDF فقط، الحجم بين 100KB و 15MB.</p>

        {errors.length ? (
          <ul className="error-list full-row">
            {errors.map((message, index) => (
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
