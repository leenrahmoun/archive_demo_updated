import { useEffect, useRef, useState } from "react";
import { getDocumentPdfBlob } from "../api/documentsApi";
import {
  extractPdfRequestErrorMessage,
  startPdfPrintSession,
  startPdfReadingSession,
} from "../utils/documentPdf";
import { AlertMessage } from "./AlertMessage";

export function DocumentPdfPanel({ document, title, refreshKey }) {
  const previewRequestRef = useRef(0);
  const previewUrlRef = useRef("");
  const printSessionRef = useRef(null);
  const [isPreviewVisible, setIsPreviewVisible] = useState(false);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [previewUrl, setPreviewUrl] = useState("");
  const [pdfError, setPdfError] = useState("");
  const [isPrintingPdf, setIsPrintingPdf] = useState(false);
  const [isOpeningExternalPdf, setIsOpeningExternalPdf] = useState(false);

  function replacePreviewUrl(nextUrl) {
    previewUrlRef.current = nextUrl;
    setPreviewUrl((currentUrl) => {
      if (currentUrl) {
        URL.revokeObjectURL(currentUrl);
      }
      return nextUrl;
    });
  }

  function clearPreviewUrl() {
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = "";
    }
    setPreviewUrl("");
  }

  function clearPrintSession() {
    if (printSessionRef.current) {
      printSessionRef.current.cleanup?.();
      printSessionRef.current = null;
    }
  }

  async function loadPreview({ fallbackMessage }) {
    const requestId = previewRequestRef.current + 1;
    previewRequestRef.current = requestId;

    try {
      setIsPreviewLoading(true);
      setPdfError("");

      const pdfBlob = await getDocumentPdfBlob(document.id);
      if (previewRequestRef.current !== requestId) {
        return "";
      }

      const nextPreviewUrl = URL.createObjectURL(pdfBlob);
      replacePreviewUrl(nextPreviewUrl);
      return nextPreviewUrl;
    } catch (requestError) {
      if (previewRequestRef.current !== requestId) {
        return "";
      }

      clearPreviewUrl();
      setPdfError(await extractPdfRequestErrorMessage(requestError, fallbackMessage));
      return "";
    } finally {
      if (previewRequestRef.current === requestId) {
        setIsPreviewLoading(false);
      }
    }
  }

  async function handlePreviewToggle() {
    if (isPreviewVisible) {
      setIsPreviewVisible(false);
      return;
    }

    setIsPreviewVisible(true);
    if (!previewUrl && !isPreviewLoading) {
      await loadPreview({ fallbackMessage: "تعذر تحميل ملف PDF للقراءة." });
    }
  }

  async function handlePrint() {
    setIsPrintingPdf(true);
    setPdfError("");

    try {
      clearPrintSession();
      const printSession = await startPdfPrintSession({
        documentTitle: document.doc_name || `الوثيقة ${document.doc_number || document.id}`,
        loadPdfBlob: () => getDocumentPdfBlob(document.id),
      });
      printSessionRef.current = printSession;
    } catch (requestError) {
      const fallbackMessage =
        requestError instanceof Error && requestError.message
          ? requestError.message
          : "تعذر تجهيز ملف PDF للطباعة.";
      setPdfError(await extractPdfRequestErrorMessage(requestError, fallbackMessage));
    } finally {
      setIsPrintingPdf(false);
    }
  }

  async function handleOpenInNewTab() {
    setIsOpeningExternalPdf(true);
    setPdfError("");

    try {
      await startPdfReadingSession({
        documentTitle: document.doc_name || `الوثيقة ${document.doc_number || document.id}`,
        loadPdfBlob: () => getDocumentPdfBlob(document.id),
      });
    } catch (requestError) {
      const fallbackMessage =
        requestError instanceof Error && requestError.message
          ? requestError.message
          : "تعذر فتح ملف PDF في صفحة جديدة.";
      setPdfError(await extractPdfRequestErrorMessage(requestError, fallbackMessage));
    } finally {
      setIsOpeningExternalPdf(false);
    }
  }

  useEffect(() => {
    setIsPreviewVisible(false);
    setIsPreviewLoading(false);
    setIsOpeningExternalPdf(false);
    setPdfError("");
    clearPreviewUrl();
    clearPrintSession();
    previewRequestRef.current += 1;

    return () => {
      previewRequestRef.current += 1;
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
        previewUrlRef.current = "";
      }
      clearPrintSession();
    };
  }, [document.id]);

  useEffect(() => {
    if (!isPreviewVisible) {
      return undefined;
    }

    const requestId = previewRequestRef.current + 1;
    previewRequestRef.current = requestId;

    async function refreshVisiblePreview() {
      try {
        setIsPreviewLoading(true);
        setPdfError("");

        const pdfBlob = await getDocumentPdfBlob(document.id);
        if (previewRequestRef.current !== requestId) {
          return;
        }

        const nextPreviewUrl = URL.createObjectURL(pdfBlob);
        replacePreviewUrl(nextPreviewUrl);
      } catch (requestError) {
        if (previewRequestRef.current !== requestId) {
          return;
        }

        clearPreviewUrl();
        setPdfError(await extractPdfRequestErrorMessage(requestError, "تعذر تحديث معاينة ملف PDF بعد تغيير الملف."));
      } finally {
        if (previewRequestRef.current === requestId) {
          setIsPreviewLoading(false);
        }
      }
    }

    refreshVisiblePreview();
    return undefined;
  }, [document.id, isPreviewVisible, refreshKey]);

  return (
    <div className="card document-file-card">
      <div className="document-file-card__header">
        <div>
          <h3>{title}</h3>
        </div>
        <div className="document-file-card__actions">
          <button
            type="button"
            className="btn-secondary btn-compact document-file-card__utility-button"
            onClick={handlePreviewToggle}
            disabled={isPreviewLoading || isPrintingPdf || isOpeningExternalPdf}
          >
            {isPreviewVisible ? "إخفاء القراءة" : "قراءة الملف"}
          </button>
          <button
            type="button"
            className="btn-secondary btn-compact document-file-card__utility-button"
            onClick={handlePrint}
            disabled={isPreviewLoading || isPrintingPdf || isOpeningExternalPdf}
          >
            {isPrintingPdf ? "جارٍ تجهيز الطباعة..." : "طباعة الملف"}
          </button>
          <button
            type="button"
            className="btn-secondary btn-compact document-file-card__utility-button document-file-card__utility-button--wide"
            onClick={handleOpenInNewTab}
            disabled={isPreviewLoading || isPrintingPdf || isOpeningExternalPdf}
          >
            {isOpeningExternalPdf ? "جارٍ فتح الصفحة الجديدة..." : "فتح الملف في صفحة جديدة"}
          </button>
        </div>
      </div>

      <AlertMessage type="error" message={pdfError} />

      {isPreviewVisible ? (
        <div className="document-file-card__preview">
          {isPreviewLoading ? (
            <div className="document-file-card__state">
              <strong>يتم تحميل ملف PDF...</strong>
              <p>قد يستغرق فتح الملف بضع لحظات بحسب حجم الوثيقة.</p>
            </div>
          ) : previewUrl ? (
            <iframe
              src={previewUrl}
              title={`PDF ${document.doc_name || document.doc_number || document.id}`}
              className="document-file-card__frame"
            />
          ) : (
            <div className="document-file-card__state document-file-card__state--error">
              <strong>تعذر فتح ملف PDF داخل الصفحة.</strong>
              <p>تحقق من وجود الملف وصلاحية الوصول إليه ثم أعد المحاولة.</p>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
