import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getDocumentById, getDocumentPdfBlob, replaceDocumentPdf } from "../api/documentsApi";
import { useAuth } from "../auth/useAuth";
import { AlertMessage } from "../components/AlertMessage";
import { DocumentWorkflowActions } from "../components/DocumentWorkflowActions";
import { PageHeader } from "../components/PageHeader";
import { EmptyBlock, LoadingBlock } from "../components/StateBlock";
import { StatusBadge } from "../components/StatusBadge";
import { formatDate } from "../utils/format";

export function DocumentDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const fileInputRef = useRef(null);
  const [document, setDocument] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [isPdfVisible, setIsPdfVisible] = useState(false);
  const [isPdfLoading, setIsPdfLoading] = useState(false);
  const [pdfUrl, setPdfUrl] = useState("");
  const [pdfError, setPdfError] = useState("");
  const [isReplacingFile, setIsReplacingFile] = useState(false);
  const [replaceSuccess, setReplaceSuccess] = useState("");
  const [replaceError, setReplaceError] = useState("");

  function clearPdfUrl() {
    setPdfUrl((currentUrl) => {
      if (currentUrl) {
        URL.revokeObjectURL(currentUrl);
      }
      return "";
    });
  }

  async function loadPdfPreview() {
    try {
      setIsPdfLoading(true);
      setPdfError("");
      const pdfBlob = await getDocumentPdfBlob(id);
      const nextPdfUrl = URL.createObjectURL(pdfBlob);
      setPdfUrl((currentUrl) => {
        if (currentUrl) {
          URL.revokeObjectURL(currentUrl);
        }
        return nextPdfUrl;
      });
      return true;
    } catch {
      clearPdfUrl();
      setPdfError("تعذر تحميل ملف PDF.");
      return false;
    } finally {
      setIsPdfLoading(false);
    }
  }

  useEffect(() => {
    async function loadDocument() {
      try {
        setIsLoading(true);
        const result = await getDocumentById(id);
        setDocument(result);
        setError("");
      } catch {
        setDocument(null);
        setError("تعذر تحميل تفاصيل الوثيقة.");
      } finally {
        setIsLoading(false);
      }
    }

    setIsPdfVisible(false);
    setPdfError("");
    setReplaceSuccess("");
    setReplaceError("");
    clearPdfUrl();
    loadDocument();
  }, [id]);

  useEffect(() => {
    return () => {
      if (pdfUrl) {
        URL.revokeObjectURL(pdfUrl);
      }
    };
  }, [pdfUrl]);

  async function handlePdfToggle() {
    if (isPdfVisible) {
      setIsPdfVisible(false);
      return;
    }

    setIsPdfVisible(true);
    if (!pdfUrl && !isPdfLoading) {
      const didLoad = await loadPdfPreview();
      if (!didLoad) {
        setIsPdfVisible(false);
      }
    }
  }

  function handleReplaceClick() {
    fileInputRef.current?.click();
  }

  async function handleReplaceFileChange(event) {
    const input = event.target;
    const nextFile = input.files?.[0];
    if (!nextFile) {
      return;
    }

    const shouldRefreshPreview = isPdfVisible;
    setReplaceSuccess("");
    setReplaceError("");

    try {
      setIsReplacingFile(true);
      const updatedDocument = await replaceDocumentPdf(id, nextFile);
      setDocument(updatedDocument);
      clearPdfUrl();
      setPdfError("");

      if (shouldRefreshPreview) {
        setIsPdfVisible(true);
        const didLoad = await loadPdfPreview();
        if (!didLoad) {
          setIsPdfVisible(false);
        }
      } else {
        setIsPdfVisible(false);
      }

      setReplaceSuccess("تم استبدال ملف PDF بنجاح.");
    } catch (requestError) {
      const fileMessage = requestError?.response?.data?.file?.[0];
      const detail = requestError?.response?.data?.detail;
      setReplaceError(fileMessage || (Array.isArray(detail) ? detail[0] : detail) || "تعذر استبدال ملف PDF.");
    } finally {
      input.value = "";
      setIsReplacingFile(false);
    }
  }

  if (isLoading) {
    return <LoadingBlock />;
  }

  if (error) {
    return <AlertMessage type="error" message={error} />;
  }

  if (!document) {
    return <EmptyBlock message="الوثيقة غير موجودة." />;
  }

  const canReplacePdf =
    user?.role === "data_entry" &&
    user?.id === document.created_by &&
    !document.is_deleted &&
    (document.status === "draft" || document.status === "rejected");

  return (
    <section>
      <PageHeader title="تفاصيل الوثيقة" subtitle="معلومات الوثيقة وسير العمل المرتبط بها." />
      <div className="card details-grid">
        <p>
          <strong>رقم الوثيقة:</strong> {document.doc_number}
        </p>
        <p>
          <strong>اسم الوثيقة:</strong> {document.doc_name}
        </p>
        <p>
          <strong>الحالة:</strong> {document.status}
          {"  "}
          <StatusBadge status={document.status} />
          {document.is_approved_by_admin ? (
            <span style={{ color: "#d97706", fontWeight: "bold", marginRight: "8px" }}>
              (معتمد من الإدارة)
            </span>
          ) : null}
        </p>
        <p>
          <strong>رقم الإضبارة:</strong>{" "}
          <Link to={`/dossiers/${document.dossier}`}>
            {document.dossier_name || document.dossier}
          </Link>
        </p>
        <p>
          <strong>نوع الوثيقة:</strong> {document.doc_type_name || document.doc_type}
        </p>
        <p>
          <strong>أنشأها:</strong> {document.created_by_name || document.created_by}
        </p>
        <p>
          <strong>تاريخ الإنشاء:</strong> {formatDate(document.created_at)}
        </p>
        <p>
          <strong>آخر تعديل:</strong> {formatDate(document.updated_at)}
        </p>
        <p>
          <strong>المراجع:</strong> {document.reviewed_by_name || document.reviewed_by || "-"}
        </p>
        <p>
          <strong>تاريخ المراجعة:</strong> {formatDate(document.reviewed_at)}
        </p>
        <p>
          <strong>سبب الرفض:</strong> {document.rejection_reason || "-"}
        </p>
        <p>
          <strong>الحذف المنطقي:</strong> {document.is_deleted ? "نعم" : "لا"}
        </p>
        <p className="full-row path-text">
          <strong>المسار:</strong> {document.file_path}
        </p>
        <p className="full-row">
          <strong>ملاحظات:</strong> {document.notes || "-"}
        </p>
        <div className="full-row" style={{ marginTop: "1rem" }}>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf,.pdf"
            style={{ display: "none" }}
            onChange={handleReplaceFileChange}
          />
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
            <button type="button" className="btn-secondary" onClick={handlePdfToggle} disabled={isPdfLoading}>
              {isPdfVisible ? "إخفاء ملف PDF" : "عرض ملف PDF"}
            </button>
            {canReplacePdf ? (
              <button
                type="button"
                className="btn-secondary"
                onClick={handleReplaceClick}
                disabled={isReplacingFile}
              >
                {isReplacingFile ? "جارٍ استبدال الملف..." : "استبدال ملف PDF"}
              </button>
            ) : null}
            {pdfUrl ? (
              <a href={pdfUrl} target="_blank" rel="noreferrer">
                فتح في نافذة جديدة
              </a>
            ) : null}
          </div>
          {replaceSuccess ? <AlertMessage type="success" message={replaceSuccess} /> : null}
          {replaceError ? <AlertMessage type="error" message={replaceError} /> : null}
          {pdfError ? <AlertMessage type="error" message={pdfError} /> : null}
          {isPdfVisible ? (
            <div
              style={{
                marginTop: "0.75rem",
                minHeight: "720px",
                border: "1px solid #d8e1ef",
                borderRadius: "12px",
                overflow: "hidden",
                background: "#f8fbff",
              }}
            >
              {pdfUrl ? (
                <object
                  data={pdfUrl}
                  type="application/pdf"
                  width="100%"
                  height="720"
                  aria-label={`PDF ${document.doc_name}`}
                >
                  <div className="state-block info" style={{ margin: "1rem" }}>
                    المتصفح لا يعرض ملف PDF داخل الصفحة. استخدم رابط الفتح في نافذة جديدة.
                  </div>
                </object>
              ) : (
                <div className="state-block info" style={{ margin: "1rem" }}>
                  جارٍ تحميل ملف PDF...
                </div>
              )}
            </div>
          ) : null}
        </div>

        {document.status === "draft" || document.status === "rejected" ? (
          <p className="full-row" style={{ marginTop: "1rem" }}>
            <Link to={`/documents/${document.id}/edit`} className="button">
              تعديل الوثيقة
            </Link>
          </p>
        ) : null}
      </div>

      <DocumentWorkflowActions
        document={document}
        onDocumentChanged={(updated) => {
          setDocument(updated);
        }}
      />
    </section>
  );
}
