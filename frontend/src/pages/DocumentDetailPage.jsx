import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getDocumentById } from "../api/documentsApi";
import { AlertMessage } from "../components/AlertMessage";
import { DocumentWorkflowActions } from "../components/DocumentWorkflowActions";
import { PageHeader } from "../components/PageHeader";
import { EmptyBlock, LoadingBlock } from "../components/StateBlock";
import { StatusBadge } from "../components/StatusBadge";
import { formatDate } from "../utils/format";

export function DocumentDetailPage() {
  const { id } = useParams();
  const [document, setDocument] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getDocumentById(id)
      .then((result) => {
        setDocument(result);
        setError("");
      })
      .catch(() => {
        setDocument(null);
        setError("تعذر تحميل تفاصيل الوثيقة.");
      })
      .finally(() => setIsLoading(false));
  }, [id]);

  if (isLoading) {
    return <LoadingBlock />;
  }

  if (error) {
    return <AlertMessage type="error" message={error} />;
  }

  if (!document) {
    return <EmptyBlock message="الوثيقة غير موجودة." />;
  }

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
          <strong>المراجع:</strong> {document.reviewed_by_name || document.reviewed_by || "—" }
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
        
        {document.status === "draft" || document.status === "rejected" ? (
          <p className="full-row" style={{ marginTop: "1rem" }}>
            <Link to={`/documents/${document.id}/edit`} className="button">تعديل الوثيقة</Link>
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
