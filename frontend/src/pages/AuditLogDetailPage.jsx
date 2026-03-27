import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getAuditLogById } from "../api/auditLogsApi";
import { AlertMessage } from "../components/AlertMessage";
import { PageHeader } from "../components/PageHeader";
import { EmptyBlock, LoadingBlock } from "../components/StateBlock";
import { formatDate } from "../utils/format";

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

const FIELD_LABELS = {
  status: "الحالة",
  submitted_at: "تاريخ التقديم",
  reviewed_at: "تاريخ المراجعة",
  reviewed_by: "تمت المراجعة بواسطة",
  rejection_reason: "سبب الرفض",
  doc_name: "اسم الوثيقة",
  doc_number: "رقم الوثيقة",
  file_path: "مسار الملف",
  mime_type: "نوع الملف",
  file_size_kb: "حجم الملف",
  created_by: "أنشأ بواسطة",
  dossier: "الإضبارة",
  doc_type: "نوع الوثيقة",
  is_deleted: "محذوف",
  deleted_at: "تاريخ الحذف",
  deleted_by: "تم الحذف بواسطة",
  updated_at: "تاريخ التحديث",
};

const STATUS_LABELS = {
  draft: "مسودة",
  pending: "معلقة",
  approved: "معتمدة",
  rejected: "مرفوضة",
};

function formatFieldValue(key, value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  if (typeof value === "boolean") {
    return value ? "نعم" : "لا";
  }

  // Format status values
  if (key === "status" && STATUS_LABELS[value]) {
    return STATUS_LABELS[value];
  }

  // Format timestamps (ISO strings)
  if (typeof value === "string" && value.match(/^\d{4}-\d{2}-\d{2}T/)) {
    return formatDate(value);
  }

  // Format objects/arrays
  if (typeof value === "object") {
    return JSON.stringify(value);
  }

  return String(value);
}

function getFieldLabel(key) {
  return FIELD_LABELS[key] || key;
}

function getEventDescription(action, entityType) {
  const entityLabel = ENTITY_LABELS[entityType] || entityType;

  const eventDescriptions = {
    create: `تم إنشاء ${entityLabel}`,
    update: `تم تحديث ${entityLabel}`,
    submit: `تم تقديم ${entityLabel}`,
    approve: `تمت الموافقة على ${entityLabel}`,
    reject: `تم رفض ${entityLabel}`,
    delete: `تم حذف ${entityLabel}`,
    restore: `تم استعادة ${entityLabel}`,
  };

  return eventDescriptions[action] || `${ACTION_LABELS[action] || action} ${entityLabel}`;
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

  if (isLoading) {
    return <LoadingBlock />;
  }

  if (error) {
    return <AlertMessage type="error" message={error} />;
  }

  if (!log) {
    return <EmptyBlock message="السجل غير موجود." />;
  }

  const eventTitle = getEventDescription(log.action, log.entity_type);
  const entityLabel = ENTITY_LABELS[log.entity_type] || log.entity_type;

  const oldValues = log.old_values || {};
  const newValues = log.new_values || {};

  const allKeys = Array.from(new Set([...Object.keys(oldValues), ...Object.keys(newValues)]))
    .filter(key => key !== "rejection_reason" || log.action === "reject");

  return (
    <section>
      <PageHeader title="تفاصيل سجل التدقيق" subtitle="عرض واضح ومفهوم لتفاصيل العملية والتغييرات" />

      {/* Event Summary Card */}
      <div className="card">
        <div className="event-header">{eventTitle}</div>

        <div className="event-details-grid">
          <div className="event-detail-row">
            <span className="detail-label">الفاعل:</span>
            <span className="detail-value">{log.actor?.username || "غير معروف"}</span>
          </div>
          <div className="event-detail-row">
            <span className="detail-label">الدور:</span>
            <span className="detail-value">{log.actor?.role || "—"}</span>
          </div>
          {log.entity_type === "document" && log.entity_reference && (
            <div className="event-detail-row">
              <span className="detail-label">نوع الوثيقة:</span>
              <span className="detail-value">{log.entity_reference}</span>
            </div>
          )}
          <div className="event-detail-row">
            <span className="detail-label">التاريخ:</span>
            <span className="detail-value">{formatDate(log.created_at)}</span>
          </div>
          {log.ip_address && (
            <div className="event-detail-row">
              <span className="detail-label">عنوان IP:</span>
              <span className="detail-value">{log.ip_address}</span>
            </div>
          )}
        </div>
      </div>

      {/* Changes Card */}
      {allKeys.length > 0 && (
        <div className="card">
          <div className="changes-header">التغييرات</div>
          <div className="changes-table">
            <div className="changes-row changes-header-row">
              <div className="changes-cell changes-field-header">الحقل</div>
              <div className="changes-cell changes-old-header">قبل</div>
              <div className="changes-cell changes-new-header">بعد</div>
            </div>
            {allKeys.map((key) => {
              const oldVal = formatFieldValue(key, oldValues[key]);
              const newVal = formatFieldValue(key, newValues[key]);
              const hasChanged = oldVal !== newVal;

              return (
                <div key={key} className={`changes-row ${hasChanged ? "has-changed" : ""}`}>
                  <div className="changes-cell changes-field">{getFieldLabel(key)}</div>
                  <div className="changes-cell changes-old">{oldVal}</div>
                  <div className="changes-cell changes-new">{newVal}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {!allKeys.length && (
        <div className="card">
          <p className="no-changes">لا توجد تفاصيل تغيير متاحة لهذا السجل.</p>
        </div>
      )}
    </section>
  );
}
