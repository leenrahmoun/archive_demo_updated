import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getAdminDashboard } from "../api/adminDashboardApi";
import { AlertMessage } from "../components/AlertMessage";
import { BrandLockup } from "../components/BrandLockup";
import { PageHeader } from "../components/PageHeader";
import { EmptyBlock, LoadingBlock } from "../components/StateBlock";
import { formatDate } from "../utils/format";

const numberFormatter = new Intl.NumberFormat("ar");

const EMPLOYEE_SORT_OPTIONS = [
  { value: "documents_created_count", label: "الأكثر إنشاءً للوثائق" },
  { value: "dossiers_created_count", label: "الأكثر إنشاءً للأضابير" },
  { value: "submissions_count", label: "الأكثر إرسالًا للمراجعة" },
  { value: "draft_documents_count", label: "الأعلى في المسودات" },
  { value: "rejected_documents_count", label: "الأعلى في المرفوضات" },
];

const AUDITOR_SORT_OPTIONS = [
  { value: "pending_documents_in_scope", label: "الأعلى ضغطًا حاليًا" },
  { value: "reviewed_documents_count", label: "الأكثر مراجعة" },
  { value: "approved_by_auditor_count", label: "الأكثر اعتمادًا" },
  { value: "rejected_by_auditor_count", label: "الأكثر رفضًا" },
];

const DASHBOARD_MAIN_SECTIONS = [
  {
    value: "indicators",
    label: "المؤشرات",
    description: "ملخص تنفيذي سريع يوضح حالة العمل الحالية ووضع الفريق وأهم الإشارات الإدارية.",
  },
  {
    value: "analytics",
    label: "التحليلات",
    description: "قراءة بصرية واضحة لحركة الوثائق واتجاهات الاعتماد والرفض وتوزيع الحالات.",
  },
  {
    value: "operations",
    label: "الأداء التشغيلي",
    description: "متابعة تشغيلية تركز على أداء مدخلي البيانات والمدققين ومن يتحمل أكبر ضغط عمل.",
  },
  {
    value: "recent",
    label: "النشاط الحديث",
    description: "قوائم مختصرة تسهّل متابعة آخر الوثائق والقرارات وسجل التدقيق بدون ازدحام بصري.",
  },
];

const DASHBOARD_OPERATIONAL_SECTIONS = [
  {
    value: "data-entry",
    label: "مدخلو البيانات",
    description: "من ينجز أكثر، ومن تتراكم لديه المسودات أو الرفض أو عبء المتابعة.",
  },
  {
    value: "auditors",
    label: "المدققون",
    description: "من لديه أعلى ضغط مراجعة، ومن يراجع ويعتمد أكثر داخل النطاق.",
  },
  {
    value: "top-performers",
    label: "الأعلى أداء",
    description: "ترتيبات جاهزة لأفضل المساهمين ونقاط الضغط التشغيلية داخل الفريق.",
  },
];

const TONE_COLORS = {
  default: "#0B6B5C",
  success: "#1F7B59",
  warning: "#C5A86A",
  danger: "#C14F4F",
  neutral: "#7A8C84",
  muted: "#9AA69F",
};

function formatCount(value) {
  return numberFormatter.format(value || 0);
}

function formatActivityDate(value) {
  return value ? formatDate(value) : "لا يوجد نشاط مسجل";
}

function getEmployeeOpenLoad(item) {
  return (item.draft_documents_count || 0) + (item.pending_documents_count || 0) + (item.rejected_documents_count || 0);
}

function getEmployeeReviewBacklog(item) {
  return (item.pending_documents_count || 0) + (item.rejected_documents_count || 0);
}

function getAuditorBacklog(item) {
  return (item.pending_documents_in_scope || 0) + (item.rejected_documents_in_scope || 0);
}

function getTopItem(items, metricGetter) {
  if (!items.length) {
    return null;
  }
  return [...items].sort(
    (left, right) =>
      metricGetter(right) - metricGetter(left) ||
      String(left.display_name || left.label || left.username || "").localeCompare(
        String(right.display_name || right.label || right.username || ""),
        "ar",
      ),
  )[0];
}

function sortPeople(items, metricKey, fallbackMetricKey) {
  return [...items].sort(
    (left, right) =>
      (right[metricKey] || 0) - (left[metricKey] || 0) ||
      (right[fallbackMetricKey] || 0) - (left[fallbackMetricKey] || 0) ||
      String(left.display_name || "").localeCompare(String(right.display_name || ""), "ar") ||
      (left.user_id || 0) - (right.user_id || 0),
  );
}

function buildDonutBackground(items) {
  const total = items.reduce((sum, item) => sum + (item.value || 0), 0);
  if (!total) {
    return "conic-gradient(#e8edf5 0deg 360deg)";
  }

  let currentAngle = 0;
  const segments = items.map((item) => {
    const slice = ((item.value || 0) / total) * 360;
    const start = currentAngle;
    const end = currentAngle + slice;
    currentAngle = end;
    return `${TONE_COLORS[item.tone] || TONE_COLORS.default} ${start}deg ${end}deg`;
  });

  return `conic-gradient(${segments.join(", ")})`;
}

function SectionHeader({ title, description, actions }) {
  return (
    <div className="dashboard-modern__section-header">
      <div>
        <h3>{title}</h3>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="dashboard-modern__actions">{actions}</div> : null}
    </div>
  );
}

function DashboardTabBar({ items, activeValue, onChange, ariaLabel, compact = false }) {
  return (
    <div
      className={`dashboard-tab-bar${compact ? " dashboard-tab-bar--compact" : ""}`}
      role="tablist"
      aria-label={ariaLabel}
    >
      {items.map((item) => {
        const isActive = item.value === activeValue;

        return (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={isActive}
            className={`dashboard-tab-bar__button${isActive ? " is-active" : ""}${compact ? " dashboard-tab-bar__button--compact" : ""}`}
            onClick={() => onChange(item.value)}
          >
            <span className="dashboard-tab-bar__label">{item.label}</span>
            {item.description ? <span className="dashboard-tab-bar__description">{item.description}</span> : null}
          </button>
        );
      })}
    </div>
  );
}

function KpiCard({ label, value, helperText, tone = "default" }) {
  return (
    <article className={`dashboard-kpi-card dashboard-kpi-card--${tone}`}>
      <span className="dashboard-kpi-card__label">{label}</span>
      <strong className="dashboard-kpi-card__value">{formatCount(value)}</strong>
      {helperText ? <p className="dashboard-kpi-card__helper">{helperText}</p> : null}
    </article>
  );
}

function InsightChip({ label, value, helperText, tone = "default" }) {
  return (
    <article className={`dashboard-insight-chip dashboard-insight-chip--${tone}`}>
      <span className="dashboard-insight-chip__label">{label}</span>
      <strong className="dashboard-insight-chip__value">{value}</strong>
      {helperText ? <span className="dashboard-insight-chip__helper">{helperText}</span> : null}
    </article>
  );
}

function MiniStat({ label, value, tone = "default" }) {
  return (
    <div className={`dashboard-mini-stat dashboard-mini-stat--${tone}`}>
      <span>{label}</span>
      <strong>{formatCount(value)}</strong>
    </div>
  );
}

function WorkSegments({ segments, total }) {
  const safeTotal = Math.max(total, 1);

  return (
    <div className="dashboard-work-segments">
      <div className="dashboard-work-segments__track">
        {segments.map((segment) => (
          <span
            key={segment.key}
            className={`dashboard-work-segments__part dashboard-work-segments__part--${segment.tone}`}
            style={{ width: `${((segment.value || 0) / safeTotal) * 100}%` }}
            title={`${segment.label}: ${formatCount(segment.value)}`}
          />
        ))}
      </div>
      <div className="dashboard-work-segments__legend">
        {segments.map((segment) => (
          <span key={segment.key}>
            {segment.label}: {formatCount(segment.value)}
          </span>
        ))}
      </div>
    </div>
  );
}

function DonutCard({ chart, className = "" }) {
  const items = chart?.items || [];

  return (
    <article className={`card dashboard-panel dashboard-panel--status dashboard-panel--analytics ${className}`.trim()}>
      <SectionHeader
        title="توزيع حالات الوثائق"
        description="الوثائق النشطة حسب حالتها الحالية."
      />

      <div className="dashboard-status-card">
        <div className="dashboard-donut" style={{ background: buildDonutBackground(items) }}>
          <div className="dashboard-donut__center">
            <strong>{formatCount(chart?.total || 0)}</strong>
            <span>وثيقة نشطة</span>
          </div>
        </div>

        <div className="dashboard-legend">
          {items.map((item) => (
            <article key={item.key} className="dashboard-legend__item">
              <div className="dashboard-legend__head">
                <span
                  className="dashboard-legend__swatch"
                  style={{ backgroundColor: TONE_COLORS[item.tone] || TONE_COLORS.default }}
                />
                <strong className="dashboard-legend__label">{item.label}</strong>
              </div>
              <span className="dashboard-legend__value">{formatCount(item.value)}</span>
            </article>
          ))}
        </div>
      </div>
    </article>
  );
}

function TimelineCard({ title, description, items, grouped = false, className = "" }) {
  const maxValue = Math.max(
    1,
    ...items.map((item) => (grouped ? Math.max(item.approved_value || 0, item.rejected_value || 0) : item.value || 0)),
  );

  return (
    <article className={`card dashboard-panel dashboard-panel--analytics ${className}`.trim()}>
      <SectionHeader title={title} description={description} />

      <div className={`dashboard-timeline${grouped ? " dashboard-timeline--grouped" : ""}`}>
        {items.map((item) => (
          <div key={item.date} className="dashboard-timeline__column">
            <div className="dashboard-timeline__bars">
              {grouped ? (
                <>
                  <div
                    className="dashboard-timeline__bar dashboard-timeline__bar--success"
                    style={{ height: `${((item.approved_value || 0) / maxValue) * 100}%` }}
                  />
                  <div
                    className="dashboard-timeline__bar dashboard-timeline__bar--danger"
                    style={{ height: `${((item.rejected_value || 0) / maxValue) * 100}%` }}
                  />
                </>
              ) : (
                <div
                  className="dashboard-timeline__bar dashboard-timeline__bar--single"
                  style={{ height: `${((item.value || 0) / maxValue) * 100}%` }}
                />
              )}
            </div>
            <strong className="dashboard-timeline__value">
              {grouped
                ? `${formatCount(item.approved_value)} / ${formatCount(item.rejected_value)}`
                : formatCount(item.value)}
            </strong>
            <span className="dashboard-timeline__label">{item.label}</span>
          </div>
        ))}
      </div>
    </article>
  );
}

function RankedListCard({ title, description, items, renderMeta, renderBar }) {
  const maxValue = Math.max(1, ...items.map((item) => item.value || 0));

  return (
    <article className="card dashboard-panel">
      <SectionHeader title={title} description={description} />

      {items.length ? (
        <div className="dashboard-ranked-list">
          {items.map((item, index) => (
            <article key={`${item.user_id}-${index}`} className="dashboard-ranked-list__item">
              <div className="dashboard-ranked-list__head">
                <span className="dashboard-ranked-list__rank">{formatCount(index + 1)}</span>
                <div className="dashboard-ranked-list__identity">
                  <strong>{item.label}</strong>
                  <span>{renderMeta(item)}</span>
                </div>
                <strong className="dashboard-ranked-list__value">{formatCount(item.value)}</strong>
              </div>
              {renderBar(item, maxValue)}
            </article>
          ))}
        </div>
      ) : (
        <EmptyBlock message="لا توجد بيانات كافية لعرض هذا المؤشر الآن." />
      )}
    </article>
  );
}

function UserActivityCard({ userActivity, adminReviewActivity, inactiveUsers }) {
  return (
    <article className="card dashboard-panel">
      <SectionHeader
        title="وضع الفريق"
        description="نظرة سريعة على توزيع الأدوار، المستخدمين النشطين، ونشاط المدير في الاعتماد والرفض."
      />

      <div className="dashboard-mini-stats-grid">
        <MiniStat label="مدخلو البيانات" value={userActivity.total_data_entry_users} />
        <MiniStat label="المدققون" value={userActivity.total_auditors} />
        <MiniStat label="القراء" value={userActivity.total_readers} tone="neutral" />
        <MiniStat label="المستخدمون النشطون" value={userActivity.total_active_users} tone="success" />
        <MiniStat
          label="بلا مدقق"
          value={userActivity.data_entry_users_without_assigned_auditor}
          tone="warning"
        />
        <MiniStat
          label="مدققون بلا تكليف"
          value={userActivity.auditors_with_zero_assigned_data_entry_users}
          tone="muted"
        />
      </div>

      <div className="dashboard-activity-notes">
        <div className="dashboard-activity-note">
          <strong>اعتمادات المدير</strong>
          <span>{formatCount(adminReviewActivity.approved_by_admin_count)}</span>
        </div>
        <div className="dashboard-activity-note">
          <strong>رفض المدير</strong>
          <span>{formatCount(adminReviewActivity.rejected_by_admin_count)}</span>
        </div>
        <div className="dashboard-activity-note dashboard-activity-note--wide">
          <strong>آخر مراجعة إدارية</strong>
          <span>{formatActivityDate(adminReviewActivity.latest_admin_review_at)}</span>
        </div>
      </div>

      <div className="dashboard-panel__footer dashboard-panel__footer--stacked">
        <strong>الأقل نشاطًا أو بلا نشاط</strong>
        <span>
          {inactiveUsers.length
            ? inactiveUsers.slice(0, 4).map((item) => item.display_name).join("، ")
            : "لا توجد حالات خمول واضحة في البيانات الحالية."}
        </span>
      </div>
    </article>
  );
}

function WorkflowOverviewCard({ workflow }) {
  return (
    <article className="card dashboard-panel">
      <SectionHeader
        title="وضع سير العمل"
        description="بطاقة سريعة توضّح أين تتركز الوثائق المفتوحة وما الذي يحتاج متابعة إدارية أو تصحيحًا."
      />

      <div className="dashboard-mini-stats-grid">
        <MiniStat label="بانتظار مراجعة" value={workflow.pending_review_documents} tone="warning" />
        <MiniStat label="تحتاج تصحيحًا" value={workflow.rejected_waiting_correction_documents} tone="danger" />
        <MiniStat label="معتمدة" value={workflow.approved_documents} tone="success" />
        <MiniStat label="أُنشئت حديثًا" value={workflow.recently_created_documents} />
      </div>

      <div className="dashboard-panel__footer dashboard-panel__footer--stacked">
        <strong>نافذة المتابعة الحالية</strong>
        <span>تعرض البطاقة آخر {formatCount(workflow.recent_window_days)} أيام من النشاط الميداني.</span>
      </div>
    </article>
  );
}

function PersonCard({ rank, title, subtitle, badge, metrics, segments, footer }) {
  return (
    <article className="dashboard-person-card">
      <div className="dashboard-person-card__head">
        <span className="dashboard-person-card__rank">{formatCount(rank)}</span>
        <div className="dashboard-person-card__identity">
          <strong>{title}</strong>
          <span>{subtitle}</span>
        </div>
        {badge ? <span className="dashboard-person-card__badge">{badge}</span> : null}
      </div>

      <div className="dashboard-person-card__metrics">
        {metrics.map((metric) => (
          <div key={metric.label} className={`dashboard-person-card__metric dashboard-person-card__metric--${metric.tone || "default"}`}>
            <span>{metric.label}</span>
            <strong>{formatCount(metric.value)}</strong>
          </div>
        ))}
      </div>

      <WorkSegments segments={segments.segments} total={segments.total} />

      <div className="dashboard-person-card__footer">{footer}</div>
    </article>
  );
}

function DataEntryPerformanceCard({ rank, item }) {
  const openLoad = getEmployeeOpenLoad(item);
  const reviewBacklog = getEmployeeReviewBacklog(item);
  const primaryMetrics = [
    { label: "الوثائق المنشأة", value: item.documents_created_count, tone: "success" },
    { label: "الأضابير المنشأة", value: item.dossiers_created_count, tone: "default" },
    { label: "الإرسال للمراجعة", value: item.submissions_count, tone: "warning" },
  ];
  const statusMetrics = [
    { label: "مسودات", value: item.draft_documents_count, tone: "neutral" },
    { label: "بانتظار مراجعة", value: item.pending_documents_count, tone: "warning" },
    { label: "مرفوضة", value: item.rejected_documents_count, tone: "danger" },
    { label: "معتمدة", value: item.approved_documents_count, tone: "success" },
  ];

  return (
    <article className="dashboard-data-entry-card">
      <div className="dashboard-data-entry-card__hero">
        <div className="dashboard-data-entry-card__identity-block">
          <div className="dashboard-data-entry-card__identity-row">
            <span className="dashboard-data-entry-card__rank">{formatCount(rank)}</span>
            <div className="dashboard-data-entry-card__identity">
              <strong>{item.display_name}</strong>
              <span>{item.username}</span>
            </div>
          </div>

          <div className="dashboard-data-entry-card__meta">
            <span className="dashboard-data-entry-card__badge">
              {item.assigned_auditor_name ? `المدقق المسؤول: ${item.assigned_auditor_name}` : "بدون مدقق مرتبط"}
            </span>
            <span className="dashboard-data-entry-card__meta-note">
              آخر نشاط: {formatActivityDate(item.last_activity_at)}
            </span>
          </div>
        </div>

        <div className="dashboard-data-entry-card__primary-metrics">
          {primaryMetrics.map((metric) => (
            <div
              key={metric.label}
              className={`dashboard-data-entry-card__primary-metric dashboard-data-entry-card__primary-metric--${metric.tone}`}
            >
              <span>{metric.label}</span>
              <strong>{formatCount(metric.value)}</strong>
            </div>
          ))}
        </div>
      </div>

      <div className="dashboard-data-entry-card__body">
        <section className="dashboard-data-entry-card__panel">
          <div className="dashboard-data-entry-card__panel-head">
            <div>
              <h4>حالة الوثائق الحالية</h4>
              <p>تفصيل سريع يوضح أين يتركز العمل الحالي لهذا الموظف.</p>
            </div>
            <div className="dashboard-data-entry-card__panel-total">
              <span>الحمل المفتوح</span>
              <strong>{formatCount(openLoad)}</strong>
            </div>
          </div>

          <div className="dashboard-data-entry-card__status-grid">
            {statusMetrics.map((metric) => (
              <div
                key={metric.label}
                className={`dashboard-data-entry-card__status-metric dashboard-data-entry-card__status-metric--${metric.tone}`}
              >
                <span>{metric.label}</span>
                <strong>{formatCount(metric.value)}</strong>
              </div>
            ))}
          </div>
        </section>

        <section className="dashboard-data-entry-card__panel dashboard-data-entry-card__panel--soft">
          <div className="dashboard-data-entry-card__panel-head">
            <div>
              <h4>ضغط المتابعة والتصحيح</h4>
              <p>ما يحتاج مراجعة أو إعادة عمل قبل الإغلاق النهائي.</p>
            </div>
            <div className="dashboard-data-entry-card__panel-total">
              <span>عبء المراجعة</span>
              <strong>{formatCount(reviewBacklog)}</strong>
            </div>
          </div>

          <div className="dashboard-data-entry-card__summary-grid">
            <div className="dashboard-data-entry-card__summary-item">
              <span>الحمل المفتوح</span>
              <strong>{formatCount(openLoad)}</strong>
            </div>
            <div className="dashboard-data-entry-card__summary-item">
              <span>ينتظر مراجعة</span>
              <strong>{formatCount(item.pending_documents_count)}</strong>
            </div>
            <div className="dashboard-data-entry-card__summary-item">
              <span>يحتاج تصحيحًا</span>
              <strong>{formatCount(item.rejected_documents_count)}</strong>
            </div>
          </div>

          <WorkSegments
            segments={[
              { key: "draft", label: "مسودات", value: item.draft_documents_count, tone: "neutral" },
              { key: "pending", label: "بانتظار مراجعة", value: item.pending_documents_count, tone: "warning" },
              { key: "rejected", label: "مرفوضة", value: item.rejected_documents_count, tone: "danger" },
            ]}
            total={Math.max(1, openLoad)}
          />
        </section>
      </div>
    </article>
  );
}

function RecentDocumentsCard({ title, items, emptyMessage, metaBuilder }) {
  return (
    <article className="card dashboard-panel">
      <SectionHeader title={title} />

      {items.length ? (
        <div className="dashboard-recent-list">
          {items.map((item) => (
            <article key={item.id} className="dashboard-recent-list__item">
              <div className="dashboard-recent-list__content">
                <strong>{item.doc_name}</strong>
                <span>{`${item.doc_number} - ${item.dossier_name}`}</span>
                <span>{item.doc_type_name}</span>
                <small>{metaBuilder(item)}</small>
              </div>
              <Link to={`/documents/${item.id}`} className="btn-secondary dashboard-recent-list__link">
                عرض
              </Link>
            </article>
          ))}
        </div>
      ) : (
        <EmptyBlock message={emptyMessage} />
      )}
    </article>
  );
}

function RecentAuditEventsCard({ items }) {
  return (
    <article className="card dashboard-panel">
      <SectionHeader title="أحدث أحداث سجل التدقيق" />

      {items.length ? (
        <div className="dashboard-recent-list">
          {items.map((item) => (
            <article key={item.id} className="dashboard-recent-list__item">
              <div className="dashboard-recent-list__content">
                <strong>{item.change_summary}</strong>
                <span>{`${item.actor_name} - ${item.entity_label}`}</span>
                <small>{formatDate(item.created_at)}</small>
              </div>
              <Link to={`/audit-logs/${item.id}`} className="btn-secondary dashboard-recent-list__link">
                عرض
              </Link>
            </article>
          ))}
        </div>
      ) : (
        <EmptyBlock message="لا توجد أحداث تدقيق حديثة." />
      )}
    </article>
  );
}

export function AdminDashboardPage() {
  const [dashboard, setDashboard] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [employeeSort, setEmployeeSort] = useState("documents_created_count");
  const [auditorSort, setAuditorSort] = useState("pending_documents_in_scope");
  const [activeDashboardSection, setActiveDashboardSection] = useState("indicators");
  const [activeOperationalSection, setActiveOperationalSection] = useState("data-entry");

  useEffect(() => {
    let isActive = true;

    getAdminDashboard()
      .then((result) => {
        if (!isActive) {
          return;
        }
        setDashboard(result);
        setError("");
      })
      .catch(() => {
        if (isActive) {
          setError("تعذر تحميل لوحة الإدارة الحديثة.");
        }
      })
      .finally(() => {
        if (isActive) {
          setIsLoading(false);
        }
      });

    return () => {
      isActive = false;
    };
  }, []);

  const insights = useMemo(() => {
    if (!dashboard) {
      return null;
    }

    const dataEntries = dashboard.employee_tracking.data_entry_performance;
    const auditors = dashboard.employee_tracking.auditor_performance;
    const inactiveUsers = [
      ...dataEntries.filter(
        (item) =>
          item.documents_created_count === 0 &&
          item.dossiers_created_count === 0 &&
          item.submissions_count === 0 &&
          !item.last_activity_at,
      ),
      ...auditors.filter(
        (item) =>
          item.reviewed_documents_count === 0 &&
          item.assigned_data_entry_count === 0 &&
          getAuditorBacklog(item) === 0 &&
          !item.last_activity_at,
      ),
    ];

    return {
      inactiveUsers,
      topDossierCreator: getTopItem(dataEntries, (item) => item.dossiers_created_count || 0),
      topDocumentCreator: getTopItem(dataEntries, (item) => item.documents_created_count || 0),
      topSubmitter: getTopItem(dataEntries, (item) => item.submissions_count || 0),
      highestDraftOwner: getTopItem(dataEntries, (item) => item.draft_documents_count || 0),
      highestRejectedOwner: getTopItem(dataEntries, (item) => item.rejected_documents_count || 0),
      busiestAuditor: getTopItem(auditors, (item) => getAuditorBacklog(item)),
      mostActiveAuditor: getTopItem(auditors, (item) => item.reviewed_documents_count || 0),
    };
  }, [dashboard]);

  const sortedDataEntries = useMemo(() => {
    if (!dashboard) {
      return [];
    }
    return sortPeople(dashboard.employee_tracking.data_entry_performance, employeeSort, "documents_created_count");
  }, [dashboard, employeeSort]);

  const sortedAuditors = useMemo(() => {
    if (!dashboard) {
      return [];
    }
    return sortPeople(dashboard.employee_tracking.auditor_performance, auditorSort, "reviewed_documents_count");
  }, [dashboard, auditorSort]);

  if (isLoading) {
    return <LoadingBlock message="جاري تحميل لوحة الإدارة الحديثة..." />;
  }

  if (error) {
    return <AlertMessage type="error" message={error} />;
  }

  if (!dashboard || !insights) {
    return <EmptyBlock message="لا توجد بيانات متاحة لعرض لوحة الإدارة." />;
  }

  const { summary, workflow, user_activity, employee_tracking, charts, recent_activity } = dashboard;

  const summaryCards = [
    { label: "إجمالي الأضابير", value: summary.total_dossiers, tone: "default", helperText: "عدد الأضابير المفتوحة في النظام." },
    { label: "إجمالي الوثائق النشطة", value: summary.total_active_documents, tone: "default", helperText: "كل الوثائق غير المحذوفة منطقيًا." },
    { label: "المسودات", value: summary.draft_documents, tone: "neutral", helperText: "وثائق ما زالت داخل مرحلة الإدخال." },
    { label: "قيد المراجعة", value: summary.pending_documents, tone: "warning", helperText: "تنتظر تدقيقًا أو قرارًا إداريًا." },
    { label: "المرفوضة", value: summary.rejected_documents, tone: "danger", helperText: "تحتاج تصحيحًا قبل إعادة الإرسال." },
    { label: "المعتمدة", value: summary.approved_documents, tone: "success", helperText: "أنهت دورة المراجعة بنجاح." },
    { label: "المحذوفة منطقيًا", value: summary.soft_deleted_documents, tone: "muted", helperText: "محفوظة تاريخيًا وخارج القوائم النشطة." },
    { label: "المستخدمون النشطون", value: summary.total_active_users, tone: "success", helperText: "الحسابات العاملة حاليًا ضمن النظام." },
  ];

  const activeDashboardSectionMeta =
    DASHBOARD_MAIN_SECTIONS.find((section) => section.value === activeDashboardSection) || DASHBOARD_MAIN_SECTIONS[0];
  const activeOperationalSectionMeta =
    DASHBOARD_OPERATIONAL_SECTIONS.find((section) => section.value === activeOperationalSection) ||
    DASHBOARD_OPERATIONAL_SECTIONS[0];

  return (
    <section className="dashboard-modern">
      <PageHeader
        title="لوحة الإدارة"
        subtitle="لوحة تنفيذية حديثة تعرض حالة العمل، إنتاجية الموظفين، ضغط المدققين، وحركة الوثائق بواجهة عربية أوضح وأسهل للمتابعة."
      />

      {activeDashboardSection === "indicators" ? (
        <section className="card dashboard-hero">
          <div className="dashboard-hero__content">
            <div className="dashboard-hero__brand">
              <BrandLockup
                compact
                title="وزارة التطوير الإداري"
                subtitle="لوحة المتابعة التنفيذية"
                note="عرض مؤسسي سريع لحالة الوثائق والفريق."
              />
            </div>
            <span className="dashboard-hero__eyebrow">متابعة تنفيذية لحظية</span>
            <h3>صورة واحدة للحمل الحالي، المخرجات، والاختناقات داخل دورة الأرشفة.</h3>
            <p>
              يوجد الآن {formatCount(workflow.pending_review_documents)} وثيقة بانتظار المراجعة، و
              {formatCount(workflow.rejected_waiting_correction_documents)} وثيقة تحتاج تصحيحًا، بينما تم
              اعتماد {formatCount(workflow.approved_documents)} وثيقة.
            </p>
          </div>

          <div className="dashboard-hero__insights">
            <InsightChip
              label="الأكثر إنشاءً للأضابير"
              value={insights.topDossierCreator ? insights.topDossierCreator.display_name : "لا يوجد"}
              helperText={insights.topDossierCreator ? `${formatCount(insights.topDossierCreator.dossiers_created_count)} أضبارة` : "لا توجد حركة"}
            />
            <InsightChip
              label="الأكثر إنشاءً للوثائق"
              value={insights.topDocumentCreator ? insights.topDocumentCreator.display_name : "لا يوجد"}
              helperText={insights.topDocumentCreator ? `${formatCount(insights.topDocumentCreator.documents_created_count)} وثيقة` : "لا توجد حركة"}
              tone="success"
            />
            <InsightChip
              label="الأكثر إرسالًا للمراجعة"
              value={insights.topSubmitter ? insights.topSubmitter.display_name : "لا يوجد"}
              helperText={insights.topSubmitter ? `${formatCount(insights.topSubmitter.submissions_count)} إرسال` : "لا توجد حركة"}
              tone="warning"
            />
            <InsightChip
              label="المدقق الأعلى ضغطًا"
              value={insights.busiestAuditor ? insights.busiestAuditor.display_name : "لا يوجد"}
              helperText={insights.busiestAuditor ? `${formatCount(getAuditorBacklog(insights.busiestAuditor))} ملفًا يحتاج متابعة` : "لا يوجد ضغط حالي"}
              tone="danger"
            />
          </div>
        </section>
      ) : null}

      <section className="dashboard-modern__section dashboard-modern__section--kpis">
        <SectionHeader
          title="ملخص المؤشرات الرئيسية"
          description="الأرقام التي يحتاجها المدير فورًا لفهم وضع العمل النشط والوثائق المتعثرة والموارد البشرية المتاحة."
        />
        <div className="dashboard-kpi-grid">
          {summaryCards.map((card) => (
            <KpiCard key={card.label} label={card.label} value={card.value} helperText={card.helperText} tone={card.tone} />
          ))}
        </div>
      </section>

      <section className="dashboard-section-shell">
        <div className="dashboard-section-shell__head">
          <div className="dashboard-section-shell__copy">
            <span className="dashboard-section-shell__eyebrow">أقسام لوحة الإدارة</span>
            <h3>{activeDashboardSectionMeta.label}</h3>
            <p>{activeDashboardSectionMeta.description}</p>
          </div>

          <DashboardTabBar
            items={DASHBOARD_MAIN_SECTIONS}
            activeValue={activeDashboardSection}
            onChange={setActiveDashboardSection}
            ariaLabel="التنقل بين أقسام لوحة الإدارة"
          />
        </div>
      </section>

      {activeDashboardSection === "indicators" ? (
        <section className="dashboard-modern__section dashboard-modern__section--indicators">
          <div className="dashboard-indicators-grid">
            <WorkflowOverviewCard workflow={workflow} />
            <UserActivityCard
              userActivity={user_activity}
              adminReviewActivity={employee_tracking.admin_review_activity}
              inactiveUsers={insights.inactiveUsers}
            />
          </div>
        </section>
      ) : null}

      {activeDashboardSection === "analytics" ? (
        <section className="dashboard-modern__section dashboard-modern__section--analytics">
          <SectionHeader title="التحليلات البصرية" description="عرض سريع لاتجاهات الإنشاء والمراجعة." />
          <div className="dashboard-analytics-grid">
            <DonutCard
              chart={charts.documents_by_status}
              className="dashboard-analytics-grid__item dashboard-analytics-grid__item--status"
            />
            <TimelineCard
              title="إنشاء الوثائق"
              description={`آخر ${formatCount(charts.documents_created_over_time.window_days)} أيام.`}
              items={charts.documents_created_over_time.items}
              className="dashboard-analytics-grid__item"
            />
            <TimelineCard
              title="قرارات المراجعة"
              description="مقارنة موجزة بين الاعتماد والرفض خلال الفترة الحالية."
              items={charts.approvals_rejections_over_time.items}
              grouped
              className="dashboard-analytics-grid__item dashboard-analytics-grid__item--wide"
            />
          </div>
        </section>
      ) : null}

      {activeDashboardSection === "operations" ? (
        <section className="dashboard-subsection-shell">
          <div className="dashboard-subsection-shell__intro">
            <span className="dashboard-subsection-shell__eyebrow">عرض تشغيلي</span>
            <strong>{activeOperationalSectionMeta.label}</strong>
            <p>{activeOperationalSectionMeta.description}</p>
          </div>

          <DashboardTabBar
            items={DASHBOARD_OPERATIONAL_SECTIONS}
            activeValue={activeOperationalSection}
            onChange={setActiveOperationalSection}
            ariaLabel="التنقل داخل الأداء التشغيلي"
            compact
          />
        </section>
      ) : null}

      {activeDashboardSection === "operations" && activeOperationalSection === "top-performers" ? (
      <section className="dashboard-modern__section">
        <SectionHeader
          title="أعلى القوائم التنفيذية"
          description="ترتيبات جاهزة لتحديد أفضل المساهمين وأين تتجمع الأعمال المتأخرة أو ضغط المراجعة."
        />
        <div className="dashboard-ranked-grid">
          <RankedListCard
            title="أفضل 5 مدخلي بيانات في إنشاء الوثائق"
            description="ترتيب مباشر بحسب حجم الإنتاج الفعلي في الوثائق."
            items={charts.top_data_entry_by_created_documents.items}
            renderMeta={(item) => `${formatCount(item.dossiers_created_count)} أضابير - ${formatCount(item.submissions_count)} إرسال`}
            renderBar={(item, maxValue) => (
              <div className="dashboard-ranked-list__bar">
                <span style={{ width: `${((item.value || 0) / maxValue) * 100}%` }} />
              </div>
            )}
          />
          <RankedListCard
            title="أعلى 5 عبءًا في المراجعة والتصحيح"
            description="يركز على من تتراكم لديه حالات الانتظار أو الرفض، مع إبراز المسودات كحمل إضافي."
            items={charts.top_data_entry_by_review_backlog.items}
            renderMeta={(item) => `مسودات: ${formatCount(item.draft_documents_count)}`}
            renderBar={(item) => (
              <WorkSegments
                segments={[
                  { key: "pending", label: "بانتظار مراجعة", value: item.pending_documents_count, tone: "warning" },
                  { key: "rejected", label: "مرفوضة", value: item.rejected_documents_count, tone: "danger" },
                ]}
                total={Math.max(1, item.pending_documents_count + item.rejected_documents_count)}
              />
            )}
          />
          <RankedListCard
            title="أعلى 5 مدققين من حيث ضغط العمل"
            description="مقارنة واضحة بين الضغط الجاري في النطاق وعدد الملفات التي راجعها كل مدقق."
            items={charts.top_auditors_by_review_workload.items}
            renderMeta={(item) => `${formatCount(item.assigned_data_entry_count)} مدخلي بيانات - ${formatCount(item.reviewed_documents_count)} مراجعة`}
            renderBar={(item) => (
              <WorkSegments
                segments={[
                  { key: "pending", label: "بانتظار مراجعة", value: item.pending_documents_in_scope, tone: "warning" },
                  { key: "rejected", label: "مرفوضة في النطاق", value: item.rejected_documents_in_scope, tone: "danger" },
                ]}
                total={Math.max(1, item.pending_documents_in_scope + item.rejected_documents_in_scope)}
              />
            )}
          />
        </div>
      </section>
      ) : null}

      {activeDashboardSection === "operations" && activeOperationalSection === "data-entry" ? (
        <section className="dashboard-modern__section">
        <SectionHeader
          title="أداء مدخلي البيانات"
          description="ترتيب حي يوضح من ينجز أكثر، من يرسل أكثر للمراجعة، ومن تتراكم لديه المسودات أو الرفض."
          actions={
            <label className="dashboard-sorter">
              <span>الترتيب حسب</span>
              <select value={employeeSort} onChange={(event) => setEmployeeSort(event.target.value)}>
                {EMPLOYEE_SORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          }
        />

        <div className="dashboard-highlight-grid">
          <InsightChip
            label="أعلى مسودات"
            value={insights.highestDraftOwner ? insights.highestDraftOwner.display_name : "لا يوجد"}
            helperText={insights.highestDraftOwner ? `${formatCount(insights.highestDraftOwner.draft_documents_count)} مسودة` : "لا توجد مسودات مرتفعة"}
            tone="neutral"
          />
          <InsightChip
            label="أعلى رفض يحتاج تصحيحًا"
            value={insights.highestRejectedOwner ? insights.highestRejectedOwner.display_name : "لا يوجد"}
            helperText={insights.highestRejectedOwner ? `${formatCount(insights.highestRejectedOwner.rejected_documents_count)} مرفوضة` : "لا توجد حالات رفض متراكمة"}
            tone="danger"
          />
          <InsightChip
            label="من دون نشاط"
            value={formatCount(insights.inactiveUsers.length)}
            helperText="عدد المستخدمين الأقل نشاطًا أو الذين لا يظهر لهم نشاط مسجل."
            tone="muted"
          />
        </div>

        {sortedDataEntries.length ? (
          <div className="dashboard-data-entry-list">
            {sortedDataEntries.map((item, index) => (
              <DataEntryPerformanceCard key={item.user_id} rank={index + 1} item={item} />
            ))}
          </div>
        ) : (
          <EmptyBlock message="لا يوجد مدخلو بيانات لعرض الأداء حاليًا." />
        )}
      </section>
      ) : null}

      {activeDashboardSection === "operations" && activeOperationalSection === "auditors" ? (
        <section className="dashboard-modern__section">
        <SectionHeader
          title="ضغط المدققين"
          description="يبين من يتحمل العبء الأكبر، ومن يراجع أكثر، وما إذا كان التوزيع الحالي يحتاج إعادة توازن."
          actions={
            <label className="dashboard-sorter">
              <span>الترتيب حسب</span>
              <select value={auditorSort} onChange={(event) => setAuditorSort(event.target.value)}>
                {AUDITOR_SORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          }
        />

        <div className="dashboard-highlight-grid">
          <InsightChip
            label="الأعلى ضغطًا حاليًا"
            value={insights.busiestAuditor ? insights.busiestAuditor.display_name : "لا يوجد"}
            helperText={insights.busiestAuditor ? `${formatCount(getAuditorBacklog(insights.busiestAuditor))} ملفًا داخل النطاق` : "لا يوجد حمل معلّق"}
            tone="warning"
          />
          <InsightChip
            label="الأكثر مراجعة"
            value={insights.mostActiveAuditor ? insights.mostActiveAuditor.display_name : "لا يوجد"}
            helperText={insights.mostActiveAuditor ? `${formatCount(insights.mostActiveAuditor.reviewed_documents_count)} مراجعة` : "لا توجد مراجعات"}
            tone="success"
          />
          <InsightChip
            label="مدققون بلا تكليف"
            value={formatCount(user_activity.auditors_with_zero_assigned_data_entry_users)}
            helperText="يساعد هذا الرقم في إعادة توزيع العمل عند الحاجة."
            tone="muted"
          />
        </div>

        {sortedAuditors.length ? (
          <div className="dashboard-people-list">
            {sortedAuditors.map((item, index) => (
              <PersonCard
                key={item.user_id}
                rank={index + 1}
                title={item.display_name}
                subtitle={item.username}
                badge={`${formatCount(item.assigned_data_entry_count)} مدخلي بيانات ضمن النطاق`}
                metrics={[
                  { label: "قيد المراجعة", value: item.pending_documents_in_scope, tone: "warning" },
                  { label: "مرفوضة في النطاق", value: item.rejected_documents_in_scope, tone: "danger" },
                  { label: "راجَع", value: item.reviewed_documents_count, tone: "default" },
                  { label: "اعتمد", value: item.approved_by_auditor_count, tone: "success" },
                ]}
                segments={{
                  total: Math.max(1, getAuditorBacklog(item)),
                  segments: [
                    { key: "pending", label: "بانتظار مراجعة", value: item.pending_documents_in_scope, tone: "warning" },
                    { key: "rejected", label: "مرفوضة في النطاق", value: item.rejected_documents_in_scope, tone: "danger" },
                  ],
                }}
                footer={
                  <>
                    <span>رفض: {formatCount(item.rejected_by_auditor_count)}</span>
                    <span>آخر نشاط: {formatActivityDate(item.last_activity_at)}</span>
                  </>
                }
              />
            ))}
          </div>
        ) : (
          <EmptyBlock message="لا يوجد مدققون لعرض الضغط الحالي." />
        )}
      </section>
      ) : null}

      {activeDashboardSection === "recent" ? (
        <section className="dashboard-modern__section">
        <SectionHeader
          title="النشاط الحديث"
          description="قوائم قصيرة وسريعة تساعد على التقاط ما يحتاج متابعة فورية من دون الغرق في تفاصيل تقنية."
        />

        <div className="dashboard-recent-grid">
          <RecentDocumentsCard
            title="أحدث الوثائق قيد المراجعة"
            items={recent_activity.latest_pending_documents}
            emptyMessage="لا توجد وثائق قيد المراجعة الآن."
            metaBuilder={(item) => `أُرسلت في ${formatDate(item.submitted_at || item.created_at)} بواسطة ${item.created_by_name}`}
          />
          <RecentDocumentsCard
            title="أحدث الوثائق المرفوضة"
            items={recent_activity.latest_rejected_documents}
            emptyMessage="لا توجد وثائق مرفوضة حاليًا."
            metaBuilder={(item) =>
              item.rejection_reason
                ? `سبب الرفض: ${item.rejection_reason}`
                : `رُفضت في ${formatDate(item.reviewed_at || item.created_at)}`
            }
          />
          <RecentDocumentsCard
            title="أحدث الوثائق المعتمدة"
            items={recent_activity.latest_approved_documents}
            emptyMessage="لا توجد وثائق معتمدة حاليًا."
            metaBuilder={(item) =>
              `اعتمدها ${item.reviewed_by_name || "غير محدد"} في ${formatDate(item.reviewed_at || item.created_at)}`
            }
          />
          <RecentAuditEventsCard items={recent_activity.latest_audit_log_events} />
        </div>
      </section>
      ) : null}
    </section>
  );
}
