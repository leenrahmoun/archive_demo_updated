const STATUS_LABELS = {
  draft: "مسودة",
  pending: "قيد المراجعة",
  approved: "معتمدة",
  rejected: "مرفوضة",
};

export function StatusBadge({ status, label }) {
  const resolvedLabel = label || STATUS_LABELS[status] || status || "-";
  return <span className={`status-badge status-${status || "unknown"}`}>{resolvedLabel}</span>;
}
