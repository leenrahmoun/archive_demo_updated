import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { getAuditorReviewQueue } from "../api/documentsApi";
import { PageHeader } from "../components/PageHeader";
import { PaginationControls } from "../components/PaginationControls";
import { EmptyBlock, LoadingBlock } from "../components/StateBlock";
import { formatDate } from "../utils/format";

const DEFAULT_PAGE_SIZE = 20;

const STATUS_LABELS = {
  pending: "قيد المراجعة",
  approved: "معتمد",
  rejected: "مرفوض",
  draft: "مسودة",
};

const STATUS_BADGE_STYLES = {
  pending: { background: "#fef3c7", color: "#92400e", border: "#fcd34d" },
  approved: { background: "#dcfce7", color: "#166534", border: "#86efac" },
  rejected: { background: "#ffe4e6", color: "#be123c", border: "#fda4af" },
  draft: { background: "#f3f4f6", color: "#374151", border: "#d1d5db" },
};

function StatusBadge({ status }) {
  const style = STATUS_BADGE_STYLES[status] || STATUS_BADGE_STYLES.draft;
  const label = STATUS_LABELS[status] || status;

  return (
    <span
      style={{
        display: "inline-block",
        padding: "0.25rem 0.5rem",
        borderRadius: "4px",
        fontSize: "0.85rem",
        fontWeight: 600,
        background: style.background,
        color: style.color,
        border: `1px solid ${style.border}`,
      }}
    >
      {label}
    </span>
  );
}

export function ReviewQueuePage() {
  const { user } = useAuth();
  const [documents, setDocuments] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [count, setCount] = useState(0);
  const [nextPage, setNextPage] = useState(null);
  const [prevPage, setPrevPage] = useState(null);

  useEffect(() => {
    fetchReviewQueue();
  }, [page, pageSize]);

  const fetchReviewQueue = async () => {
    try {
      setIsLoading(true);
      const response = await getAuditorReviewQueue({
        page,
        page_size: pageSize,
      });
      setDocuments(response.results || []);
      setCount(response.count || 0);
      setNextPage(response.next);
      setPrevPage(response.previous);
      setError("");
    } catch (err) {
      setError("تعذر تحميل قائمة المراجعة.");
    } finally {
      setIsLoading(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(count / pageSize));

  if (user?.role !== "auditor" && user?.role !== "admin") {
    return (
      <section>
        <PageHeader title="قائمة المراجعة" />
        <div className="card">
          <p>غير مصرح لك بالوصول إلى هذه الصفحة.</p>
        </div>
      </section>
    );
  }

  return (
    <section>
      <PageHeader
        title="قائمة المراجعة"
        subtitle="الوثائق المعلقة بانتظار المراجعة"
      />

      {error && (
        <div className="alert alert-error" style={{ marginBottom: "1rem" }}>
          {error}
        </div>
      )}

      {isLoading ? (
        <LoadingBlock />
      ) : (
        <div className="card">
          <table className="data-table">
            <thead>
              <tr>
                <th>رقم الإضبارة</th>
                <th>نوع الوثيقة</th>
                <th>اسم المستخدم</th>
                <th>التاريخ</th>
                <th>الحالة</th>
                <th>الإجراءات</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id}>
                  <td>{doc.dossier_name || doc.dossier || "—"}</td>
                  <td>{doc.doc_type_name || doc.doc_type || "—"}</td>
                  <td>{doc.created_by_name || doc.created_by || "—"}</td>
                  <td>{formatDate(doc.created_at)}</td>
                  <td>
                    <StatusBadge status={doc.status} />
                    {doc.is_approved_by_admin && (
                      <span
                        style={{
                          display: "block",
                          fontSize: "0.75rem",
                          color: "#166534",
                          marginTop: "0.25rem",
                        }}
                      >
                        تمت الموافقة من قبل المدير
                      </span>
                    )}
                    {doc.rejection_reason && doc.reviewed_by_role === "admin" && (
                      <span
                        style={{
                          display: "block",
                          fontSize: "0.75rem",
                          color: "#991b1b",
                          marginTop: "0.25rem",
                        }}
                      >
                        تم الرفض من قبل المدير
                      </span>
                    )}
                  </td>
                  <td>
                    <Link
                      to={`/documents/${doc.id}`}
                      className="btn btn-sm"
                    >
                      مراجعة
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {!documents.length && (
            <EmptyBlock message="لا توجد وثائق بانتظار المراجعة." />
          )}
        </div>
      )}

      <PaginationControls
        page={page}
        totalPages={totalPages}
        hasPrevious={Boolean(prevPage)}
        hasNext={Boolean(nextPage)}
        onPrevious={() => {
          setIsLoading(true);
          setPage((prev) => Math.max(1, prev - 1));
        }}
        onNext={() => {
          setIsLoading(true);
          setPage((prev) => prev + 1);
        }}
      />
    </section>
  );
}
