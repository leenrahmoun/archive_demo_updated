import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getDeletedDocuments } from "../api/documentsApi";
import { useAuth } from "../auth/useAuth";
import { AlertMessage } from "../components/AlertMessage";
import { EmptyBlock, LoadingBlock } from "../components/StateBlock";
import { FilterSection } from "../components/FilterSection";
import { PageHeader } from "../components/PageHeader";
import { PaginationControls } from "../components/PaginationControls";
import { StatusBadge } from "../components/StatusBadge";
import { formatDate } from "../utils/format";

const DEFAULT_PAGE_SIZE = 20;

export function DeletedDocumentsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const subtitle = isAdmin
    ? "قائمة متابعة مستقلة للوثائق المحذوفة منطقيًا خارج القوائم التشغيلية اليومية."
    : "تعرض الوثائق التي حُذفت منطقيًا من الوثائق التي أنشأتها أنت فقط.";

  const [filters, setFilters] = useState({
    search: "",
    status: "",
    created_by: "",
    deleted_by: "",
    ordering: "-deleted_at",
  });
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState({ count: 0, results: [], next: null, previous: null });

  useEffect(() => {
    const params = { page, ...filters };
    Object.keys(params).forEach((key) => {
      if (params[key] === "") {
        delete params[key];
      }
    });

    getDeletedDocuments(params)
      .then((result) => {
        setData(result);
        setError("");
      })
      .catch(() => setError("تعذّر تحميل قائمة الوثائق المحذوفة منطقيًا."))
      .finally(() => setIsLoading(false));
  }, [page, filters]);

  const totalPages = useMemo(
    () => Math.max(1, Math.ceil((data.count || 0) / DEFAULT_PAGE_SIZE)),
    [data.count]
  );

  function onFilterChange(key, value) {
    setIsLoading(true);
    setPage(1);
    setFilters((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <section>
      <PageHeader title="الوثائق المحذوفة منطقيًا" subtitle={subtitle} />

      <FilterSection>
        <input
          placeholder="بحث: رقم الوثيقة / اسم الوثيقة / رقم الإضبارة / المسار"
          aria-label="بحث في الوثائق المحذوفة منطقيًا"
          value={filters.search}
          onChange={(event) => onFilterChange("search", event.target.value)}
        />
        <select value={filters.status} onChange={(event) => onFilterChange("status", event.target.value)}>
          <option value="">كل الحالات الأصلية</option>
          <option value="draft">مسودة</option>
          <option value="pending">قيد المراجعة</option>
          <option value="approved">معتمدة</option>
          <option value="rejected">مرفوضة</option>
        </select>
        {isAdmin ? (
          <input
            placeholder="أنشأها المستخدم"
            value={filters.created_by}
            onChange={(event) => onFilterChange("created_by", event.target.value)}
          />
        ) : null}
        <input
          placeholder="حذفها المستخدم"
          value={filters.deleted_by}
          onChange={(event) => onFilterChange("deleted_by", event.target.value)}
        />
        <select value={filters.ordering} onChange={(event) => onFilterChange("ordering", event.target.value)}>
          <option value="-deleted_at">الأحدث حذفًا</option>
          <option value="deleted_at">الأقدم حذفًا</option>
          <option value="-created_at">الأحدث إنشاءً</option>
          <option value="created_at">الأقدم إنشاءً</option>
          <option value="status">الحالة تصاعديًا</option>
          <option value="-status">الحالة تنازليًا</option>
        </select>
      </FilterSection>

      <AlertMessage type="error" message={error} />

      {isLoading ? <LoadingBlock /> : null}

      {!isLoading ? (
        <>
          <p className="deleted-documents-page__summary muted">
            إجمالي الوثائق المحذوفة منطقيًا ضمن نطاقك: {data.count}
          </p>

          <div className="card">
            <div className="table-wrapper">
              <table className="data-table deleted-documents-page__table">
                <thead>
                  <tr>
                    <th>رقم الوثيقة</th>
                    <th>اسم الوثيقة</th>
                    <th>الحالة عند الحذف</th>
                    <th>الإضبارة</th>
                    <th>نوع الوثيقة</th>
                    {isAdmin ? <th>أنشأها</th> : null}
                    <th>حُذفت بواسطة</th>
                    <th>تاريخ الحذف</th>
                    <th>إجراء</th>
                  </tr>
                </thead>
                <tbody>
                  {data.results.map((doc) => (
                    <tr key={doc.id}>
                      <td>{doc.doc_number}</td>
                      <td>{doc.doc_name}</td>
                      <td>
                        <StatusBadge status={doc.status} label={doc.status_display_label} />
                      </td>
                      <td>{doc.dossier_name || doc.dossier || "-"}</td>
                      <td>{doc.doc_type_name || doc.doc_type || "-"}</td>
                      {isAdmin ? <td>{doc.created_by_name || doc.created_by || "-"}</td> : null}
                      <td>{doc.deleted_by_name || "-"}</td>
                      <td className="deleted-documents-page__deleted-at">{formatDate(doc.deleted_at)}</td>
                      <td className="deleted-documents-page__action-cell">
                        <Link
                          to={`/documents/${doc.id}?include_deleted=1`}
                          className="btn-secondary deleted-documents-page__view-link"
                        >
                          عرض
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {!data.results.length ? <EmptyBlock message="لا توجد وثائق محذوفة منطقيًا ضمن نطاقك الحالي." /> : null}
          </div>
        </>
      ) : null}

      <PaginationControls
        page={page}
        totalPages={totalPages}
        hasPrevious={Boolean(data.previous)}
        hasNext={Boolean(data.next)}
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
