import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getDocuments } from "../api/documentsApi";
import { getDocumentTypes } from "../api/lookupsApi";
import { AlertMessage } from "../components/AlertMessage";
import { EmptyBlock, LoadingBlock } from "../components/StateBlock";
import { FilterSection } from "../components/FilterSection";
import { PageHeader } from "../components/PageHeader";
import { PaginationControls } from "../components/PaginationControls";
import { StatusBadge } from "../components/StatusBadge";

const DEFAULT_PAGE_SIZE = 20;

export function DocumentsListPage() {
  const [documentTypes, setDocumentTypes] = useState([]);
  const [filters, setFilters] = useState({
    search: "",
    status: "",
    doc_type: "",
    dossier: "",
    created_by: "",
    reviewed_by: "",
    is_deleted: "",
    ordering: "",
    page_size: DEFAULT_PAGE_SIZE,
  });
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState({ count: 0, results: [], next: null, previous: null });

  useEffect(() => {
    getDocumentTypes().then(setDocumentTypes).catch(() => setDocumentTypes([]));
  }, []);

  useEffect(() => {
    const params = { page, ...filters };
    Object.keys(params).forEach((key) => {
      if (params[key] === "") {
        delete params[key];
      }
    });

    getDocuments(params)
      .then((result) => {
        setData(result);
        setError("");
      })
      .catch(() => setError("تعذر تحميل قائمة الوثائق."))
      .finally(() => setIsLoading(false));
  }, [page, filters]);

  const totalPages = useMemo(
    () => Math.max(1, Math.ceil((data.count || 0) / Number(filters.page_size || DEFAULT_PAGE_SIZE))),
    [data.count, filters.page_size]
  );

  function onFilterChange(key, value) {
    setIsLoading(true);
    setPage(1);
    setFilters((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <section>
      <PageHeader title="قائمة الوثائق" subtitle="عرض حالة الوثائق مع أدوات تصفية وترتيب." />

      <FilterSection>
        <input
          placeholder="بحث: رقم الوثيقة / الاسم / المسار"
          value={filters.search}
          onChange={(e) => onFilterChange("search", e.target.value)}
        />
        <select value={filters.status} onChange={(e) => onFilterChange("status", e.target.value)}>
          <option value="">كل الحالات</option>
          <option value="draft">draft</option>
          <option value="pending">pending</option>
          <option value="approved">approved</option>
          <option value="rejected">rejected</option>
        </select>
        <select value={filters.doc_type} onChange={(e) => onFilterChange("doc_type", e.target.value)}>
          <option value="">كل الأنواع</option>
          {documentTypes.map((docType) => (
            <option key={docType.id} value={docType.id}>
              {docType.name}
            </option>
          ))}
        </select>
        <input
          placeholder="رقم الإضبارة (id)"
          value={filters.dossier}
          onChange={(e) => onFilterChange("dossier", e.target.value)}
        />
        <input
          placeholder="أنشأها المستخدم (id)"
          value={filters.created_by}
          onChange={(e) => onFilterChange("created_by", e.target.value)}
        />
        <input
          placeholder="راجعها المستخدم (id أو null)"
          value={filters.reviewed_by}
          onChange={(e) => onFilterChange("reviewed_by", e.target.value)}
        />
        <select value={filters.is_deleted} onChange={(e) => onFilterChange("is_deleted", e.target.value)}>
          <option value="">افتراضي (غير محذوفة)</option>
          <option value="false">غير محذوفة</option>
          <option value="true">محذوفة منطقيا</option>
        </select>
        <select value={filters.ordering} onChange={(e) => onFilterChange("ordering", e.target.value)}>
          <option value="">الترتيب الافتراضي (الأحدث)</option>
          <option value="status">status تصاعدي</option>
          <option value="-status">status تنازلي</option>
          <option value="created_at">created_at تصاعدي</option>
          <option value="-created_at">created_at تنازلي</option>
          <option value="reviewed_at">reviewed_at تصاعدي</option>
          <option value="-reviewed_at">reviewed_at تنازلي</option>
        </select>
        <select value={filters.page_size} onChange={(e) => onFilterChange("page_size", Number(e.target.value))}>
          <option value={10}>10</option>
          <option value={20}>20</option>
          <option value={50}>50</option>
        </select>
      </FilterSection>

      <AlertMessage type="error" message={error} />
      {isLoading ? <LoadingBlock /> : null}

      {!isLoading ? (
        <div className="card">
          <table className="data-table">
            <thead>
              <tr>
                <th>رقم الوثيقة</th>
                <th>اسم الوثيقة</th>
                <th>الحالة</th>
                <th>الإضبارة</th>
                <th>نوع الوثيقة</th>
                <th>تفاصيل</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((doc) => (
                <tr key={doc.id}>
                  <td>{doc.doc_number}</td>
                  <td>{doc.doc_name}</td>
                  <td>
                    <StatusBadge status={doc.status} />
                  </td>
                  <td>{doc.dossier}</td>
                  <td>{doc.doc_type}</td>
                  <td>
                    <Link to={`/documents/${doc.id}`}>عرض</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!data.results.length ? <EmptyBlock message="لا توجد نتائج." /> : null}
        </div>
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
