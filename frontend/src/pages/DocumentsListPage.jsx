import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getDocuments } from "../api/documentsApi";
import { getDocumentTypes } from "../api/lookupsApi";
import { useAuth } from "../auth/useAuth";
import { AlertMessage } from "../components/AlertMessage";
import { EmptyBlock, LoadingBlock } from "../components/StateBlock";
import { FilterSection } from "../components/FilterSection";
import { PageHeader } from "../components/PageHeader";
import { PaginationControls } from "../components/PaginationControls";
import { StatusBadge } from "../components/StatusBadge";

const DEFAULT_PAGE_SIZE = 20;

export function DocumentsListPage() {
  const { user } = useAuth();
  const isAuditor = user?.role === "auditor";
  const isReader = user?.role === "reader";
  const subtitle = isAuditor
    ? "عرض الوثائق ضمن نطاق مدخلي البيانات المرتبطين بك."
    : isReader
      ? "الوثائق المعتمدة المتاحة للقراءة مع أدوات بحث مبسطة."
      : "عرض حالة الوثائق مع أدوات تصفية وترتيب.";

  const [documentTypes, setDocumentTypes] = useState([]);
  const [filters, setFilters] = useState({
    search: "",
    status: "",
    doc_type: "",
    dossier: "",
    created_by: "",
    reviewed_by: "",
    ordering: "",
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
      <PageHeader title="قائمة الوثائق" subtitle={subtitle} />
      {isAuditor ? (
        <AlertMessage
          type="info"
          message="يمكنك تصفح الوثائق المعلقة والمرفوضة والمعتمدة ضمن نطاقك فقط، دون صلاحيات تعديل المحتوى."
        />
      ) : null}
      <FilterSection>
        <input
          placeholder={
            isReader
              ? "بحث: رقم الوثيقة / اسم الوثيقة / رقم الإضبارة"
              : "بحث: رقم الوثيقة / اسم الوثيقة / رقم الإضبارة / المسار"
          }
          aria-label={
            isReader
              ? "بحث: رقم الوثيقة / اسم الوثيقة / رقم الإضبارة"
              : "بحث: رقم الوثيقة / اسم الوثيقة / رقم الإضبارة / المسار"
          }
          value={filters.search}
          onChange={(event) => onFilterChange("search", event.target.value)}
        />
        {!isReader ? (
          <select value={filters.status} onChange={(event) => onFilterChange("status", event.target.value)}>
            <option value="">كل الحالات</option>
            {!isAuditor ? <option value="draft">draft</option> : null}
            <option value="pending">pending</option>
            <option value="approved">approved</option>
            <option value="rejected">rejected</option>
          </select>
        ) : null}
        <select value={filters.doc_type} onChange={(event) => onFilterChange("doc_type", event.target.value)}>
          <option value="">كل الأنواع</option>
          {documentTypes.map((docType) => (
            <option key={docType.id} value={docType.id}>
              {docType.name}
            </option>
          ))}
        </select>
        <input
          placeholder="رقم الإضبارة أو جزء منه"
          value={filters.dossier}
          onChange={(event) => onFilterChange("dossier", event.target.value)}
        />
        {!isReader ? (
          <>
            <input
              placeholder="أنشأها المستخدم (اسم أو id)"
              value={filters.created_by}
              onChange={(event) => onFilterChange("created_by", event.target.value)}
            />
            <input
              placeholder="راجعها المستخدم (اسم أو id)"
              value={filters.reviewed_by}
              onChange={(event) => onFilterChange("reviewed_by", event.target.value)}
            />
            <select value={filters.ordering} onChange={(event) => onFilterChange("ordering", event.target.value)}>
              <option value="">الترتيب الافتراضي (الأحدث)</option>
              <option value="status">status تصاعدي</option>
              <option value="-status">status تنازلي</option>
              <option value="created_at">created_at تصاعدي</option>
              <option value="-created_at">created_at تنازلي</option>
              <option value="reviewed_at">reviewed_at تصاعدي</option>
              <option value="-reviewed_at">reviewed_at تنازلي</option>
            </select>
          </>
        ) : (
          <select value={filters.ordering} onChange={(event) => onFilterChange("ordering", event.target.value)}>
            <option value="">الأحدث وفق تاريخ الإنشاء</option>
            <option value="created_at">الأقدم وفق تاريخ الإنشاء</option>
          </select>
        )}
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
                <th>ملاحظات</th>
                <th>تفاصيل</th>
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
                  <td>{doc.dossier_name || doc.dossier}</td>
                  <td>{doc.doc_type_name || doc.doc_type}</td>
                  <td>{doc.notes || "-"}</td>
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
