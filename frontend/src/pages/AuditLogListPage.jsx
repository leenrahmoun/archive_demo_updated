import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getAuditLogs } from "../api/auditLogsApi";
import { AlertMessage } from "../components/AlertMessage";
import { FilterSection } from "../components/FilterSection";
import { PageHeader } from "../components/PageHeader";
import { PaginationControls } from "../components/PaginationControls";
import { EmptyBlock, LoadingBlock } from "../components/StateBlock";
import {
  AUDIT_ACTION_LABELS,
  getAuditActorPrimary,
  getAuditActorSecondary,
  getAuditDisplaySummary,
  getAuditEventTitle,
  getAuditRoleLabel,
} from "../utils/auditLogPresentation";
import { formatDate } from "../utils/format";

const DEFAULT_PAGE_SIZE = 20;

const ACTION_BADGE_STYLES = {
  create: { background: "#e8f8ee", color: "#166534", border: "#b8e2c7" },
  update: { background: "#f0f9ff", color: "#075985", border: "#bae6fd" },
  submit: { background: "#fef3c7", color: "#92400e", border: "#fcd34d" },
  approve: { background: "#dcfce7", color: "#166534", border: "#86efac" },
  reject: { background: "#ffe4e6", color: "#be123c", border: "#fda4af" },
  replace_file: { background: "#eef2ff", color: "#3730a3", border: "#c7d2fe" },
  delete: { background: "#f3f4f6", color: "#374151", border: "#d1d5db" },
  restore: { background: "#f5f3ff", color: "#5b21b6", border: "#c4b5fd" },
};

function ActionBadge({ action, label }) {
  const style = ACTION_BADGE_STYLES[action] || ACTION_BADGE_STYLES.update;
  const displayLabel = label || AUDIT_ACTION_LABELS[action] || action;

  return (
    <span
      style={{
        display: "inline-block",
        padding: "0.25rem 0.5rem",
        borderRadius: "999px",
        fontSize: "0.82rem",
        fontWeight: 700,
        background: style.background,
        color: style.color,
        border: `1px solid ${style.border}`,
      }}
    >
      {displayLabel}
    </span>
  );
}

export function AuditLogListPage() {
  const [filters, setFilters] = useState({
    search: "",
    action: "",
    date_from: "",
    date_to: "",
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
      <PageHeader
        title="سجل التدقيق"
      />

      <div className="card control-panel-card--accent audit-log-filter-card">
        <div className="audit-log-filter-card__header">
        </div>

        <FilterSection>
          <input
            placeholder="ابحث باسم المستخدم أو الإجراء أو اسم الوثيقة / الإضبارة أو ملخص العملية"
            aria-label="بحث سجل التدقيق"
            value={filters.search}
            onChange={(event) => onFilterChange("search", event.target.value)}
          />
          <select value={filters.action} onChange={(event) => onFilterChange("action", event.target.value)}>
            <option value="">كل الإجراءات</option>
            <option value="create">إنشاء</option>
            <option value="update">تحديث</option>
            <option value="submit">إرسال للمراجعة</option>
            <option value="approve">اعتماد</option>
            <option value="reject">رفض</option>
            <option value="replace_file">استبدال الملف</option>
            <option value="delete">حذف</option>
            <option value="restore">استعادة</option>
          </select>
          <label className="audit-log-filter-card__field">
            <span>من تاريخ</span>
            <input
              type="date"
              aria-label="من تاريخ"
              value={filters.date_from}
              onChange={(event) => onFilterChange("date_from", event.target.value)}
            />
          </label>
          <label className="audit-log-filter-card__field">
            <span>إلى تاريخ</span>
            <input
              type="date"
              aria-label="إلى تاريخ"
              value={filters.date_to}
              onChange={(event) => onFilterChange("date_to", event.target.value)}
            />
          </label>
        </FilterSection>
      </div>

      <AlertMessage type="error" message={error} />
      {isLoading ? <LoadingBlock /> : null}

      {!isLoading ? (
        <div className="card">
          <table className="data-table">
            <thead>
              <tr>
                <th>الحدث</th>
                <th>المنفذ</th>
                <th>المرجع</th>
                <th>الملخص</th>
                <th>التاريخ</th>
                <th>التفاصيل</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((log) => (
                <tr key={log.id}>
                  <td>
                    <div className="audit-log-list__event">
                      <ActionBadge action={log.action} label={log.action_label} />
                      <strong>{getAuditEventTitle(log)}</strong>
                      <span className="muted">{log.entity_display || log.entity_label || "—"}</span>
                    </div>
                  </td>
                  <td>
                    <div className="audit-log-list__actor">
                      <strong>{getAuditActorPrimary(log)}</strong>
                      {getAuditActorSecondary(log) ? (
                        <span className="muted">{getAuditActorSecondary(log)}</span>
                      ) : null}
                      <span className="audit-log-list__role">{getAuditRoleLabel(log.actor?.role)}</span>
                    </div>
                  </td>
                  <td>
                    <div className="audit-log-list__reference">
                      <strong>{log.entity_display || log.entity_label || "—"}</strong>
                      {log.entity_reference && log.entity_reference !== log.entity_display ? (
                        <span className="muted">{log.entity_reference}</span>
                      ) : null}
                    </div>
                  </td>
                  <td>
                    <div className="audit-log-list__summary">{getAuditDisplaySummary(log)}</div>
                  </td>
                  <td>{formatDate(log.created_at)}</td>
                  <td>
                    <Link to={`/audit-logs/${log.id}`} className="btn btn-sm">
                      عرض التفاصيل
                    </Link>
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
