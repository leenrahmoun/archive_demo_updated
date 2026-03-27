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

const ACTION_LABELS = {
  create: "إنشاء",
  update: "تحديث",
  submit: "تقديم",
  approve: "موافقة",
  reject: "رفض",
  delete: "حذف",
  restore: "استعادة",
};

const ENTITY_LABELS = {
  document: "وثيقة",
  dossier: "إضبارة",
  user: "مستخدم",
};

const ACTION_BADGE_STYLES = {
  create: { background: "#e8f8ee", color: "#166534", border: "#b8e2c7" },
  update: { background: "#f0f9ff", color: "#075985", border: "#bae6fd" },
  submit: { background: "#fef3c7", color: "#92400e", border: "#fcd34d" },
  approve: { background: "#dcfce7", color: "#166534", border: "#86efac" },
  reject: { background: "#ffe4e6", color: "#be123c", border: "#fda4af" },
  delete: { background: "#f3f4f6", color: "#374151", border: "#d1d5db" },
  restore: { background: "#f5f3ff", color: "#5b21b6", border: "#c4b5fd" },
};

function getEventDisplay(action, entityType) {
  const actionLabel = ACTION_LABELS[action] || action;
  const entityLabel = ENTITY_LABELS[entityType] || entityType;
  return `${actionLabel} ${entityLabel}`;
}

function ActionBadge({ action }) {
  const style = ACTION_BADGE_STYLES[action] || ACTION_BADGE_STYLES.update;
  const label = ACTION_LABELS[action] || action;

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

export function AuditLogListPage() {
  const [filters, setFilters] = useState({
    action: "",
    actor: "",
    model: "",
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
      <PageHeader title="سجل التدقيق" subtitle="سجل العمليات والتغييرات في النظام" />

      <FilterSection>
        <select value={filters.action} onChange={(e) => onFilterChange("action", e.target.value)}>
          <option value="">كل الإجراءات</option>
          <option value="create">إنشاء</option>
          <option value="update">تحديث</option>
          <option value="submit">تقديم</option>
          <option value="approve">موافقة</option>
          <option value="reject">رفض</option>
          <option value="delete">حذف</option>
          <option value="restore">استعادة</option>
        </select>
        <input placeholder="المستخدم (id أو username)" value={filters.actor} onChange={(e) => onFilterChange("actor", e.target.value)} />
        <input placeholder="نوع الكيان (مثال: document)" value={filters.model} onChange={(e) => onFilterChange("model", e.target.value)} />
        <input placeholder="رقم الكيان" value={filters.object_id} onChange={(e) => onFilterChange("object_id", e.target.value)} />
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
                <th>الحدث</th>
                <th>الفاعل</th>
                <th>نوع الوثيقة</th>
                <th>التاريخ</th>
                <th>التفاصيل</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((log) => (
                <tr key={log.id}>
                  <td>
                    <ActionBadge action={log.action} />
                    <span style={{ marginRight: "0.5rem" }}>
                      {ENTITY_LABELS[log.entity_type] || log.entity_type}
                    </span>
                  </td>
                  <td>{log.actor?.username || "—"}</td>
                  <td>
                    {log.entity_type === "document" && log.entity_reference
                      ? log.entity_reference
                      : ENTITY_LABELS[log.entity_type] || log.entity_type}
                  </td>
                  <td>{formatDate(log.created_at)}</td>
                  <td>
                    <Link to={`/audit-logs/${log.id}`} className="btn btn-sm">عرض التفاصيل</Link>
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
