import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { createDocument, updateDocument, getDocumentById } from "../api/documentsApi";
import { DocumentTypeAutocomplete } from "../components/DocumentTypeAutocomplete";
import { getDocumentTypes } from "../api/lookupsApi";
import { flattenErrors } from "../utils/errors";
import { PageHeader } from "../components/PageHeader";
import { LoadingBlock } from "../components/StateBlock";

const MIN_FILE_SIZE_KB = 100;
const MAX_FILE_SIZE_KB = 15360;

function initialFormState() {
  return {
    doc_type: "",
    doc_number: "",
    doc_name: "",
    notes: "",
  };
}

export function DocumentFormPage() {
  const navigate = useNavigate();
  const { id, dossierId } = useParams();
  const isEditMode = Boolean(id);

  const [documentTypes, setDocumentTypes] = useState([]);
  const [form, setForm] = useState(initialFormState);
  const [selectedFile, setSelectedFile] = useState(null);
  const [errors, setErrors] = useState([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingInitial, setIsLoadingInitial] = useState(isEditMode);
  const [existingDoc, setExistingDoc] = useState(null);

  useEffect(() => {
    getDocumentTypes().then(setDocumentTypes).catch(() => setDocumentTypes([]));

    if (isEditMode) {
      getDocumentById(id)
        .then((doc) => {
          setExistingDoc(doc);
          setForm({
            doc_type: doc.doc_type?.toString() || "",
            doc_number: doc.doc_number || "",
            doc_name: doc.doc_name || "",
            notes: doc.notes || "",
          });
        })
        .catch(() => {
          setErrors(["تعذر تحميل تفاصيل الوثيقة."]);
        })
        .finally(() => setIsLoadingInitial(false));
    }
  }, [id, isEditMode]);

  const fileSizeKb = useMemo(() => {
    if (!selectedFile) {
      return null;
    }
    return Math.ceil(selectedFile.size / 1024);
  }, [selectedFile]);

  function onFileChange(event) {
    const file = event.target.files?.[0] || null;
    setSelectedFile(file);
    setErrors([]);
  }

  async function onSubmit(event) {
    event.preventDefault();
    setErrors([]);

    if (!form.doc_type) {
      setErrors(["يرجى اختيار نوع الوثيقة من القائمة المقترحة."]);
      return;
    }

    if (!selectedFile && !isEditMode) {
      setErrors(["يجب اختيار ملف PDF للوثيقة."]);
      return;
    }

    if (selectedFile) {
      if (selectedFile.type !== "application/pdf") {
        setErrors(["نوع الملف غير مدعوم. يجب أن يكون PDF فقط."]);
        return;
      }
      if (fileSizeKb < MIN_FILE_SIZE_KB || fileSizeKb > MAX_FILE_SIZE_KB) {
        setErrors([`حجم الملف يجب أن يكون بين ${MIN_FILE_SIZE_KB}KB و ${MAX_FILE_SIZE_KB}KB.`]);
        return;
      }
    }

    setIsSubmitting(true);
    try {
      if (isEditMode) {
        let finalFileSizeKb = existingDoc?.file_size_kb;
        let finalFilePath = existingDoc?.file_path;
        let finalMimeType = existingDoc?.mime_type || "application/pdf";

        if (selectedFile) {
          finalFileSizeKb = fileSizeKb;
          finalFilePath = `uploads/dossier_${dossierId}/${selectedFile.name}`;
          finalMimeType = selectedFile.type;
        }

        const payload = {
          doc_type: Number(form.doc_type),
          doc_number: form.doc_number,
          doc_name: form.doc_name,
          file_path: finalFilePath,
          file_size_kb: finalFileSizeKb,
          mime_type: finalMimeType,
          notes: form.notes || "",
        };

        await updateDocument(id, payload);
        navigate(`/documents/${id}`);
      } else {
        const payload = new FormData();
        payload.append("dossier", String(Number(dossierId)));
        payload.append("doc_type", form.doc_type);
        payload.append("doc_number", form.doc_number);
        payload.append("doc_name", form.doc_name);
        payload.append("notes", form.notes || "");
        payload.append("file", selectedFile);

        const created = await createDocument(payload);
        navigate(`/documents/${created.id}`);
      }
    } catch (err) {
      const backendErrors = flattenErrors(err?.response?.data);
      setErrors(backendErrors.length ? backendErrors : ["فشل حفظ الوثيقة."]);
    } finally {
      setIsSubmitting(false);
    }
  }

  if (isLoadingInitial) {
    return <LoadingBlock />;
  }

  return (
    <section>
      <PageHeader
        title={isEditMode ? "تعديل الوثيقة" : "إضافة وثيقة جديدة"}
        subtitle={isEditMode ? "تعديل بيانات الوثيقة" : `إضافة وثيقة للإضبارة رقم ${dossierId}`}
      />
      <form className="card form-grid" onSubmit={onSubmit}>
        <DocumentTypeAutocomplete
          options={documentTypes}
          value={form.doc_type}
          selectedLabel={existingDoc?.doc_type_name || ""}
          onChange={(nextValue) => {
            setErrors([]);
            setForm((prev) => ({ ...prev, doc_type: nextValue }));
          }}
          required
        />
        <input placeholder="رقم الوثيقة" value={form.doc_number} onChange={(e) => setForm((p) => ({ ...p, doc_number: e.target.value }))} required />
        <input placeholder="اسم الوثيقة" value={form.doc_name} onChange={(e) => setForm((p) => ({ ...p, doc_name: e.target.value }))} required />
        <input placeholder="ملاحظات (اختياري)" value={form.notes} onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))} />

        <div className="full-row">
          <label className="block mb-2 text-sm">
            النسخة الإلكترونية للوثيقة (PDF)
            {isEditMode && " - اترك الحقل فارغاً للاحتفاظ بالملف الحالي"}
          </label>
          <input type="file" accept="application/pdf,.pdf" onChange={onFileChange} required={!isEditMode} />
          {isEditMode && existingDoc?.file_path && !selectedFile && (
            <p className="muted mt-1 text-sm">الملف الحالي: {existingDoc.file_path}</p>
          )}
          <p className="muted mt-1 text-sm">يسمح بملف PDF فقط، الحجم بين 100KB و 15MB.</p>
        </div>

        {errors.length ? (
          <ul className="error-list full-row">
            {errors.map((message, index) => (
              <li key={`${message}-${index}`}>{message}</li>
            ))}
          </ul>
        ) : null}

        <button type="submit" className="full-row" disabled={isSubmitting}>
          {isSubmitting ? "جاري الحفظ..." : "حفظ الوثيقة"}
        </button>
      </form>
    </section>
  );
}
