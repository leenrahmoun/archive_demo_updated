import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getAuditLogs } from "../api/auditLogsApi";
import { AlertMessage } from "../components/AlertMessage";
import { FilterSection } from "../components/FilterSection";
import { PageHeader } from "../components/PageHeader";
import { PaginationControls } from "../components/PaginationControls";
import { EmptyBlock, LoadingBlock } from "../components/StateBlock";
import { formatDate } from "../utils/format";

const DEFAULT_PAGE_SIZE = 20;

export function AuditLogListPage() {
  const [filters, setFilters] = useState({
    action: "",
    actor: "",
    model: "",
    table_name: "",
    object_id: "",
    date_from: "",
    date_to: "",
    page_size: DEFAULT_PAGE_SIZE,
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

    getAuditLogs(params)
      .then((result) => {
        setData(result);
        setError("");
      })
      .catch(() => setError("تعذر تحميل سجل التدقيق."))
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
      <PageHeader title="سجل التدقيق" subtitle="عرض أحدث العمليات أولا مع فلاتر متقدمة." />

      <FilterSection>
        <select value={filters.action} onChange={(e) => onFilterChange("action", e.target.value)}>
          <option value="">كل الإجراءات</option>
          <option value="create">create</option>
          <option value="update">update</option>
          <option value="submit">submit</option>
          <option value="approve">approve</option>
          <option value="reject">reject</option>
          <option value="delete">delete</option>
          <option value="restore">restore</option>
        </select>
        <input placeholder="المستخدم (id أو username)" value={filters.actor} onChange={(e) => onFilterChange("actor", e.target.value)} />
        <input placeholder="model (مثال: document)" value={filters.model} onChange={(e) => onFilterChange("model", e.target.value)} />
        <input placeholder="table_name (مثال: dossier)" value={filters.table_name} onChange={(e) => onFilterChange("table_name", e.target.value)} />
        <input placeholder="object_id" value={filters.object_id} onChange={(e) => onFilterChange("object_id", e.target.value)} />
        <label>
          من تاريخ
          <input type="date" value={filters.date_from} onChange={(e) => onFilterChange("date_from", e.target.value)} />
        </label>
        <label>
          إلى تاريخ
          <input type="date" value={filters.date_to} onChange={(e) => onFilterChange("date_to", e.target.value)} />
        </label>
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
                <th>ID</th>
                <th>الإجراء</th>
                <th>الكيان</th>
                <th>معرف الكيان</th>
                <th>الفاعل</th>
                <th>التاريخ</th>
                <th>تفاصيل</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((log) => (
                <tr key={log.id}>
                  <td>{log.id}</td>
                  <td>{log.action}</td>
                  <td>{log.entity_type}</td>
                  <td>{log.entity_id}</td>
                  <td>{log.actor?.username || "-"}</td>
                  <td>{formatDate(log.created_at)}</td>
                  <td>
                    <Link to={`/audit-logs/${log.id}`}>عرض</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!data.results.length ? <EmptyBlock message="لا توجد سجلات مطابقة." /> : null}
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
