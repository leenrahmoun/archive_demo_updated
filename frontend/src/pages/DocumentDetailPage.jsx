import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import {
  getDocumentById,
  getDocumentPdfBlob,
  replaceDocumentPdf,
  submitDocument,
} from "../api/documentsApi";
import { useAuth } from "../auth/useAuth";
import { AlertMessage } from "../components/AlertMessage";
import { DocumentWorkflowActions } from "../components/DocumentWorkflowActions";
import { PageHeader } from "../components/PageHeader";
import { EmptyBlock, LoadingBlock } from "../components/StateBlock";
import { StatusBadge } from "../components/StatusBadge";
import { flattenErrors } from "../utils/errors";
import { formatDate } from "../utils/format";
import { getDocumentDetailSubmitPlacement, getDocumentWorkflowActionState } from "../utils/documentWorkflow";

export function DocumentDetailPage() {
  const { id } = useParams();
  const location = useLocation();
  const { user } = useAuth();
  const fileInputRef = useRef(null);
  const pdfPrintFrameRef = useRef(null);
  const [document, setDocument] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [isPdfVisible, setIsPdfVisible] = useState(false);
  const [isPdfLoading, setIsPdfLoading] = useState(false);
  const [pdfUrl, setPdfUrl] = useState("");
  const [pdfError, setPdfError] = useState("");
  const [isReplacingFile, setIsReplacingFile] = useState(false);
  const [isSubmittingReview, setIsSubmittingReview] = useState(false);
  const [isPrintingPdf, setIsPrintingPdf] = useState(false);
  const [feedback, setFeedback] = useState({ success: "", error: "" });

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
      return nextPdfUrl;
    } catch {
      clearPdfUrl();
      setPdfError("تعذر تحميل ملف PDF.");
      return "";
    } finally {
      setIsPdfLoading(false);
    }
  }

  async function ensurePdfUrlLoaded() {
    if (pdfUrl) {
      return pdfUrl;
    }
    return loadPdfPreview();
  }

  async function refreshDocumentDetails() {
    const result = await getDocumentById(id);
    setDocument(result);
    setError("");
    return result;
  }

  function getErrorMessage(requestError, fallbackMessage) {
    const messages = flattenErrors(requestError?.response?.data);
    return messages[0] || fallbackMessage;
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
    setFeedback({
      success: location.state?.successMessage || "",
      error: "",
    });
    clearPdfUrl();
    loadDocument();
  }, [id, location.state]);

  useEffect(() => {
    return () => {
      if (pdfUrl) {
        URL.revokeObjectURL(pdfUrl);
      }
      if (pdfPrintFrameRef.current) {
        pdfPrintFrameRef.current.remove();
        pdfPrintFrameRef.current = null;
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
      const nextPdfUrl = await loadPdfPreview();
      if (!nextPdfUrl) {
        setIsPdfVisible(false);
      }
    }
  }

  async function handlePrintPdf() {
    setIsPrintingPdf(true);
    setPdfError("");

    try {
      const nextPdfUrl = await ensurePdfUrlLoaded();
      if (!nextPdfUrl) {
        return;
      }

      if (pdfPrintFrameRef.current) {
        pdfPrintFrameRef.current.remove();
        pdfPrintFrameRef.current = null;
      }

      const printFrame = window.document.createElement("iframe");
      printFrame.style.position = "fixed";
      printFrame.style.width = "0";
      printFrame.style.height = "0";
      printFrame.style.border = "0";
      printFrame.style.opacity = "0";
      printFrame.setAttribute("aria-hidden", "true");
      printFrame.src = nextPdfUrl;

      printFrame.onload = () => {
        window.setTimeout(() => {
          try {
            printFrame.contentWindow?.focus();
            printFrame.contentWindow?.print();
          } finally {
            window.setTimeout(() => {
              if (pdfPrintFrameRef.current === printFrame) {
                printFrame.remove();
                pdfPrintFrameRef.current = null;
              }
            }, 1500);
          }
        }, 250);
      };

      window.document.body.appendChild(printFrame);
      pdfPrintFrameRef.current = printFrame;
    } catch {
      setPdfError("تعذر تجهيز ملف PDF للطباعة.");
    } finally {
      setIsPrintingPdf(false);
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
    setFeedback({ success: "", error: "" });

    try {
      setIsReplacingFile(true);
      await replaceDocumentPdf(id, nextFile);
      await refreshDocumentDetails();
      clearPdfUrl();
      setPdfError("");

      if (shouldRefreshPreview) {
        setIsPdfVisible(true);
        const nextPdfUrl = await loadPdfPreview();
        if (!nextPdfUrl) {
          setIsPdfVisible(false);
        }
      } else {
        setIsPdfVisible(false);
      }

      setFeedback({ success: "تم استبدال ملف PDF بنجاح.", error: "" });
    } catch (requestError) {
      setFeedback({
        success: "",
        error: getErrorMessage(requestError, "تعذر استبدال ملف PDF."),
      });
    } finally {
      input.value = "";
      setIsReplacingFile(false);
    }
  }

  async function handleSubmitForReview({ successMessage, fallbackMessage }) {
    try {
      setIsSubmittingReview(true);
      setFeedback({ success: "", error: "" });
      await submitDocument(id);
      await refreshDocumentDetails();
      setFeedback({ success: successMessage, error: "" });
    } catch (requestError) {
      setFeedback({
        success: "",
        error: getErrorMessage(requestError, fallbackMessage),
      });
    } finally {
      setIsSubmittingReview(false);
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

  const isDraft = document.status === "draft";
  const isRejected = document.status === "rejected";
  const isDocumentCreator = user?.id === document.created_by;
  const isReader = user?.role === "reader";
  const isAuditor = user?.role === "auditor";
  const isReadOnlyViewer = isReader || isAuditor;
  const openedFromDossierCreation = Boolean(location.state?.fromDossierCreation);
  const rejectionReason = document.rejection_reason?.trim() || "لا يوجد سبب رفض مسجل";
  const compactRejectionReason = isRejected
    ? document.rejection_reason?.trim()
      ? "مذكور في تنبيه الرفض أعلاه."
      : "لا يوجد سبب رفض مسجل"
    : document.rejection_reason || "-";
  const canReplacePdf =
    user?.role === "data_entry" &&
    isDocumentCreator &&
    !document.is_deleted &&
    (isDraft || isRejected);
  const submitPlacement = getDocumentDetailSubmitPlacement(user, document);
  const canShowDraftSubmitCard = submitPlacement === "draft-card";
  const canShowRejectedResubmitAction = submitPlacement === "rejection-card";
  const canShowRejectedReplaceAction = isRejected && canReplacePdf;
  const canShowRejectedActions = canShowRejectedReplaceAction || canShowRejectedResubmitAction;
  const lowerWorkflowHideSubmitAction = submitPlacement !== "none";
  const lowerWorkflowActionState = getDocumentWorkflowActionState(user, document, {
    hideSubmitAction: lowerWorkflowHideSubmitAction,
  });
  const shouldShowWorkflowActions =
    !isReader &&
    !(
      isRejected &&
      user?.role === "data_entry"
    ) &&
    (
      lowerWorkflowActionState.showSubmit ||
      lowerWorkflowActionState.showApprove ||
      lowerWorkflowActionState.showReject ||
      lowerWorkflowActionState.showDelete
    );
  const canEditDocument =
    !document.is_deleted &&
    (user?.role === "admin" || (user?.role === "data_entry" && isDocumentCreator)) &&
    (isDraft || isRejected);
  const draftSubmitTitle = openedFromDossierCreation
    ? "تم إنشاء الإضبارة والوثيقة الأولى"
    : "الوثيقة جاهزة للإرسال للمراجعة";
  const draftSubmitHelper = openedFromDossierCreation
    ? "حُفظت الوثيقة الأولى كمسودة. راجع الملف ثم أرسلها الآن للمراجعة حتى تنتقل إلى حالة قيد المراجعة."
    : "هذه الوثيقة ما زالت مسودة. يمكنك إرسالها للمراجعة عندما تصبح جاهزة.";
  const pdfSectionTitle = isReadOnlyViewer ? "قراءة ملف PDF" : "ملف PDF";
  const pdfSectionHelper = isReader
    ? "يمكنك قراءة ملف الوثيقة وطباعته فقط. لا توجد أي صلاحيات تعديل على المحتوى."
    : isAuditor
      ? "يمكنك قراءة الملف وطباعته ضمن نطاقك المسموح فقط. لا تتاح لك أي إجراءات تعديل على الوثيقة."
      : "يمكنك قراءة ملف الوثيقة داخل الصفحة أو طباعته. تظهر إجراءات التعديل فقط عندما تكون متاحة حسب الدور والحالة.";

  return (
    <section>
      <PageHeader title="تفاصيل الوثيقة" subtitle="معلومات الوثيقة وسير العمل المرتبط بها." />

      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf,.pdf"
        style={{ display: "none" }}
        onChange={handleReplaceFileChange}
      />

      <AlertMessage type="success" message={feedback.success} />
      <AlertMessage type="error" message={feedback.error} />

      {canShowDraftSubmitCard ? (
        <div className="card draft-submit-card">
          <div className="draft-submit-card__header">
            <div>
              <h3 className="draft-submit-card__title">{draftSubmitTitle}</h3>
              <p className="draft-submit-card__helper">{draftSubmitHelper}</p>
            </div>
            <StatusBadge status={document.status} label={document.status_display_label} />
          </div>
          <div className="draft-submit-card__actions">
            <button
              type="button"
              className="btn-primary"
              onClick={() =>
                handleSubmitForReview({
                  successMessage: "تم إرسال الوثيقة للمراجعة بنجاح.",
                  fallbackMessage: "تعذر إرسال الوثيقة للمراجعة.",
                })
              }
              disabled={isSubmittingReview || isReplacingFile}
            >
              {isSubmittingReview ? "جارٍ الإرسال..." : "إرسال للمراجعة"}
            </button>
          </div>
        </div>
      ) : null}

      {isRejected ? (
        <div className="card rejection-card">
          <div className="rejection-card__header">
            <h3 className="rejection-card__title">تم رفض هذه الوثيقة</h3>
            <StatusBadge status={document.status} label={document.status_display_label} />
          </div>
          <div className="rejection-card__reason">
            <span className="rejection-card__label">سبب الرفض</span>
            <p>{rejectionReason}</p>
          </div>
          <p className="rejection-card__helper">
            يرجى تعديل الوثيقة أو استبدال ملف الـ PDF ثم إعادة إرسالها للمراجعة.
          </p>
          {canShowRejectedActions ? (
            <div className="rejection-card__actions">
              {canShowRejectedReplaceAction ? (
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={handleReplaceClick}
                  disabled={isReplacingFile || isSubmittingReview}
                >
                  {isReplacingFile ? "جارٍ استبدال الملف..." : "استبدال ملف PDF"}
                </button>
              ) : null}
              {canShowRejectedResubmitAction ? (
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() =>
                    handleSubmitForReview({
                      successMessage: "تمت إعادة إرسال الوثيقة للمراجعة بنجاح.",
                      fallbackMessage: "تعذر إعادة إرسال الوثيقة للمراجعة.",
                    })
                  }
                  disabled={isReplacingFile || isSubmittingReview}
                >
                  {isSubmittingReview ? "جارٍ إعادة الإرسال..." : "إعادة الإرسال للمراجعة"}
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="card details-grid">
        <p>
          <strong>رقم الوثيقة:</strong> {document.doc_number}
        </p>
        <p>
          <strong>اسم الوثيقة:</strong> {document.doc_name}
        </p>
        <p>
          <strong>الحالة:</strong> <StatusBadge status={document.status} label={document.status_display_label} />
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
          <strong>سبب الرفض:</strong> <span className={isRejected ? "muted" : undefined}>{compactRejectionReason}</span>
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

        {canEditDocument ? (
          <p className="full-row" style={{ marginTop: "1rem" }}>
            <Link to={`/documents/${document.id}/edit`} className="button">
              تعديل الوثيقة
            </Link>
          </p>
        ) : null}
      </div>

      <div className="card document-file-card">
        <div className="document-file-card__header">
          <div>
            <h3>{pdfSectionTitle}</h3>
            <p className="muted">{pdfSectionHelper}</p>
          </div>
          <div className="document-file-card__actions">
            <button
              type="button"
              className="btn-secondary"
              onClick={handlePdfToggle}
              disabled={isPdfLoading || isPrintingPdf}
            >
              {isPdfVisible ? "إخفاء القراءة" : "قراءة الملف"}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={handlePrintPdf}
              disabled={isPdfLoading || isPrintingPdf}
            >
              {isPrintingPdf ? "جارٍ تجهيز الطباعة..." : "طباعة الملف"}
            </button>
            {canReplacePdf && !isRejected ? (
              <button
                type="button"
                className="btn-secondary"
                onClick={handleReplaceClick}
                disabled={isReplacingFile || isPdfLoading || isPrintingPdf}
              >
                {isReplacingFile ? "جارٍ استبدال الملف..." : "استبدال ملف PDF"}
              </button>
            ) : null}
          </div>
        </div>

        {pdfUrl ? (
          <a href={pdfUrl} target="_blank" rel="noreferrer">
            فتح الملف في نافذة مستقلة
          </a>
        ) : null}

        {pdfError ? <AlertMessage type="error" message={pdfError} /> : null}

        {isPdfVisible ? (
          <div className="document-file-card__preview">
            {pdfUrl ? (
              <iframe
                src={pdfUrl}
                title={`PDF ${document.doc_name}`}
                className="document-file-card__frame"
              />
            ) : (
              <div className="state-block info" style={{ margin: "1rem" }}>
                جارٍ تحميل ملف PDF...
              </div>
            )}
          </div>
        ) : null}
      </div>

      {shouldShowWorkflowActions ? (
        <DocumentWorkflowActions
          document={document}
          hideSubmitAction={lowerWorkflowHideSubmitAction}
          onDocumentChanged={(updated) => {
            setDocument(updated);
            setFeedback({ success: "", error: "" });
          }}
        />
      ) : null}
    </section>
  );
}
