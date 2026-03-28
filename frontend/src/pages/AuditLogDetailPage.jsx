import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { getAuditLogById } from "../api/auditLogsApi";
import { AlertMessage } from "../components/AlertMessage";
import { PageHeader } from "../components/PageHeader";
import { EmptyBlock, LoadingBlock } from "../components/StateBlock";
import {
  AUDIT_ACTION_LABELS,
  getAuditActionLabel,
  getAuditActorPrimary,
  getAuditActorSecondary,
  getAuditChangeEntries,
  getAuditDisplaySummary,
  getAuditEventTitle,
  getAuditRoleLabel,
  getAuditNarratives,
  normalizeAuditValue,
} from "../utils/auditLogPresentation";
import { formatDate } from "../utils/format";

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

const CHANGE_TYPE_LABELS = {
  changed: "تغيير",
  added: "إضافة",
  removed: "إزالة",
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

function AuditValueContent({ value }) {
  if (!value) {
    return <span className="audit-log-value-empty">—</span>;
  }

  if (value.kind === "text") {
    return <div className="audit-log-value-text">{value.text}</div>;
  }

  if (value.kind === "empty") {
    return <span className="audit-log-value-empty">{value.text}</span>;
  }

  if (value.kind === "list") {
    return (
      <div className="audit-log-value-list">
        {value.items.map((item) => (
          <div key={item.id} className="audit-log-value-list__item">
            {item.label ? <strong>{item.label}</strong> : null}
            <AuditValueContent value={item.value} />
          </div>
        ))}
      </div>
    );
  }

  if (value.kind === "pairs") {
    return (
      <dl className="audit-log-value-pairs">
        {value.items.map((item) => (
          <div key={item.key} className="audit-log-value-pair">
            <dt>{item.label}</dt>
            <dd>
              <AuditValueContent value={item.value} />
            </dd>
          </div>
        ))}
      </dl>
    );
  }

  return <div className="audit-log-value-text">—</div>;
}

function DetailFact({ label, value, subtext }) {
  return (
    <div className="audit-log-fact">
      <span className="audit-log-fact__label">{label}</span>
      <strong className="audit-log-fact__value">{value || "—"}</strong>
      {subtext ? <span className="audit-log-fact__meta">{subtext}</span> : null}
    </div>
  );
}

function ChangeCard({ entry }) {
  return (
    <article className={`audit-log-change-card audit-log-change-card--${entry.changeType}`}>
      <div className="audit-log-change-card__title">
        <h4>{entry.label}</h4>
        <span className={`audit-log-change-card__badge audit-log-change-card__badge--${entry.changeType}`}>
          {CHANGE_TYPE_LABELS[entry.changeType] || "تغيير"}
        </span>
      </div>

      <div className="audit-log-change-card__grid">
        <div className="audit-log-value-panel">
          <span className="audit-log-value-panel__label">قبل</span>
          <AuditValueContent value={entry.before} />
        </div>
        <div className="audit-log-value-panel audit-log-value-panel--after">
          <span className="audit-log-value-panel__label">بعد</span>
          <AuditValueContent value={entry.after} />
        </div>
      </div>
    </article>
  );
}

export function AuditLogDetailPage() {
  const { id } = useParams();
  const [log, setLog] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getAuditLogById(id)
      .then((result) => {
        setLog(result);
        setError("");
      })
      .catch(() => {
        setLog(null);
        setError("تعذر تحميل تفاصيل سجل التدقيق.");
      })
      .finally(() => setIsLoading(false));
  }, [id]);

  const changes = useMemo(() => getAuditChangeEntries(log), [log]);
  const narratives = useMemo(() => getAuditNarratives(log), [log]);
  const eventTitle = useMemo(() => getAuditEventTitle(log), [log]);
  const eventSummary = useMemo(() => getAuditDisplaySummary(log), [log]);

  const overviewFacts = useMemo(() => {
    if (!log) {
      return [];
    }

    return [
      {
        label: "المنفذ",
        value: getAuditActorPrimary(log),
        subtext: getAuditActorSecondary(log) || getAuditRoleLabel(log.actor?.role),
      },
      {
        label: "النوع",
        value: log.entity_label || "—",
        subtext: log.entity_type || "",
      },
      {
        label: "المرجع المرتبط",
        value: log.entity_display || log.entity_label || "—",
        subtext: log.entity_reference && log.entity_reference !== log.entity_display ? log.entity_reference : "",
      },
      {
        label: "وقت العملية",
        value: formatDate(log.created_at),
        subtext: `رقم السجل: ${log.id}`,
      },
    ];
  }, [log]);

  const supportingFacts = useMemo(() => {
    if (!log) {
      return [];
    }

    const items = [];

    if (log.ip_address) {
      items.push({ label: "عنوان الشبكة", value: log.ip_address });
    }

    if (log.actor?.username && getAuditActorPrimary(log) !== log.actor.username) {
      items.push({ label: "اسم المستخدم", value: log.actor.username });
    }

    if (log.actor?.role) {
      items.push({ label: "دور المنفذ", value: getAuditRoleLabel(log.actor.role) });
    }

    return items;
  }, [log]);

  if (isLoading) {
    return <LoadingBlock />;
  }

  if (error) {
    return <AlertMessage type="error" message={error} />;
  }

  if (!log) {
    return <EmptyBlock message="السجل غير موجود." />;
  }

  return (
    <section>
      <PageHeader
        title="تفاصيل سجل التدقيق"
        subtitle="عرض منظم وواضح يبيّن من نفّذ العملية، وعلى ماذا تمت، وما الذي تغيّر بالضبط."
      />

      <div className="card audit-log-hero">
        <div className="audit-log-hero__top">
          <ActionBadge action={log.action} label={log.action_label || getAuditActionLabel(log.action)} />
          <span className="audit-log-hero__entity">{log.entity_label || "—"}</span>
        </div>
        <h3 className="audit-log-hero__title">{eventTitle}</h3>
        <p className="audit-log-hero__summary">{eventSummary}</p>

        <div className="audit-log-facts">
          {overviewFacts.map((fact) => (
            <DetailFact key={fact.label} label={fact.label} value={fact.value} subtext={fact.subtext} />
          ))}
        </div>
      </div>

      {narratives.length ? (
        <div className="audit-log-note-grid">
          {narratives.map((item) => (
            <div
              key={item.key}
              className={`card audit-log-note audit-log-note--${item.tone === "attention" ? "attention" : "neutral"}`}
            >
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </div>
          ))}
        </div>
      ) : null}

      <div className="audit-log-detail-grid">
        <div className="card">
          <div className="audit-log-section__header">
            <h3>التغييرات المسجلة</h3>
            {changes.length ? <span className="muted">{changes.length} حقول متغيرة</span> : null}
          </div>

          {changes.length ? (
            <div className="audit-log-change-list">
              {changes.map((entry) => (
                <ChangeCard key={entry.key} entry={entry} />
              ))}
            </div>
          ) : (
            <div className="audit-log-empty-state">
              لا توجد حقول متغيرة معروضة لهذا الحدث. قد تكون العملية عبارة عن تسجيل إجراء أو ملاحظة بدون تغيير مباشر في القيم.
            </div>
          )}
        </div>

        {supportingFacts.length ? (
          <div className="card">
            <div className="audit-log-section__header">
              <h3>تفاصيل إضافية</h3>
            </div>
            <div className="audit-log-supporting-grid">
              {supportingFacts.map((fact) => (
                <DetailFact key={fact.label} label={fact.label} value={fact.value} />
              ))}
            </div>
          </div>
        ) : null}

        {!changes.length && (log.old_values || log.new_values) ? (
          <div className="card">
            <div className="audit-log-section__header">
              <h3>القيم المسجلة</h3>
              <span className="muted">عرض مرن بحسب البيانات المتاحة</span>
            </div>
            <div className="audit-log-change-card__grid">
              <div className="audit-log-value-panel">
                <span className="audit-log-value-panel__label">القيم السابقة</span>
                <AuditValueContent value={normalizeAuditValue("old_values", log.old_values)} />
              </div>
              <div className="audit-log-value-panel audit-log-value-panel--after">
                <span className="audit-log-value-panel__label">القيم الحالية</span>
                <AuditValueContent value={normalizeAuditValue("new_values", log.new_values)} />
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
