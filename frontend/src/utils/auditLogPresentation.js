import { formatDate } from "./format";

export const AUDIT_ACTION_LABELS = {
  create: "إنشاء",
  update: "تحديث",
  submit: "إرسال للمراجعة",
  approve: "اعتماد",
  reject: "رفض",
  replace_file: "استبدال الملف",
  delete: "حذف",
  restore: "استعادة",
};

const AUDIT_ACTION_TITLES = {
  create: "تم إنشاء",
  update: "تم تحديث",
  submit: "تم إرسال",
  approve: "تم اعتماد",
  reject: "تم رفض",
  replace_file: "تم استبدال ملف",
  delete: "تم حذف",
  restore: "تمت استعادة",
};

export const AUDIT_ENTITY_LABELS = {
  document: "وثيقة",
  dossier: "إضبارة",
  user: "مستخدم",
};

export const AUDIT_ROLE_LABELS = {
  admin: "المدير",
  auditor: "المدقق",
  data_entry: "مدخل البيانات",
  reader: "قارئ",
};

export const AUDIT_STATUS_LABELS = {
  draft: "مسودة",
  pending: "قيد المراجعة",
  approved: "معتمدة",
  rejected: "مرفوضة",
};

export const AUDIT_FIELD_LABELS = {
  status: "الحالة",
  submitted_at: "تاريخ الإرسال",
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
  created_at: "تاريخ الإنشاء",
  date_joined: "تاريخ الانضمام",
  first_name: "الاسم الأول",
  last_name: "اسم العائلة",
  full_name: "الاسم الكامل",
  username: "اسم المستخدم",
  email: "البريد الإلكتروني",
  role: "الدور",
  is_active: "الحالة",
  assigned_auditor: "المدقق المرتبط",
  assigned_auditor_id: "المدقق المرتبط",
  file_number: "رقم الإضبارة",
  national_id: "الرقم الوطني",
  personal_id: "الرقم الذاتي",
  is_non_syrian: "الجنسية غير سورية",
  nationality_name: "الجنسية أو البلد",
  governorate: "المحافظة",
  room_number: "رقم الغرفة",
  column_number: "رقم العمود",
  shelf_number: "رقم الرف",
  notes: "ملاحظات",
  message: "ملاحظة",
};

const HIDDEN_CHANGE_KEYS = new Set(["message"]);

function isEmptyValue(value) {
  if (value === null || value === undefined || value === "") {
    return true;
  }

  if (Array.isArray(value)) {
    return value.length === 0;
  }

  if (typeof value === "object") {
    return Object.keys(value).length === 0;
  }

  return false;
}

function isIsoDateString(value) {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}(T|\b)/.test(value);
}

function normalizeUnknownLabel(key) {
  return String(key || "")
    .replaceAll("_", " ")
    .trim();
}

function comparableValue(value) {
  return JSON.stringify(value ?? null);
}

function scalarToText(key, value) {
  if (isEmptyValue(value)) {
    return "—";
  }

  if (typeof value === "boolean") {
    if (key === "is_active") {
      return value ? "نشط" : "غير نشط";
    }
    return value ? "نعم" : "لا";
  }

  if (key === "status") {
    return AUDIT_STATUS_LABELS[value] || String(value);
  }

  if (key === "role") {
    return AUDIT_ROLE_LABELS[value] || String(value);
  }

  if (key === "file_size_kb" && typeof value === "number") {
    return `${value} كيلوبايت`;
  }

  if (isIsoDateString(value)) {
    return formatDate(value);
  }

  if (typeof value === "number" && key.endsWith("_by")) {
    return `مستخدم رقم ${value}`;
  }

  if (typeof value === "number" && key === "dossier") {
    return `إضبارة رقم ${value}`;
  }

  if (typeof value === "number" && key === "doc_type") {
    return `نوع وثيقة رقم ${value}`;
  }

  return String(value);
}

export function getAuditActionLabel(action) {
  return AUDIT_ACTION_LABELS[action] || action || "—";
}

export function getAuditEntityLabel(entityType) {
  return AUDIT_ENTITY_LABELS[entityType] || entityType || "—";
}

export function getAuditFieldLabel(key) {
  return AUDIT_FIELD_LABELS[key] || normalizeUnknownLabel(key) || "تفصيل";
}

export function getAuditRoleLabel(role) {
  return AUDIT_ROLE_LABELS[role] || role || "—";
}

export function getAuditEventTitle(log) {
  const actionTitle = AUDIT_ACTION_TITLES[log?.action] || getAuditActionLabel(log?.action);
  const entityLabel = log?.entity_label || getAuditEntityLabel(log?.entity_type);
  return `${actionTitle} ${entityLabel}`;
}

export function getAuditActorPrimary(log) {
  return log?.actor?.display_name || log?.actor?.full_name || log?.actor?.username || "غير معروف";
}

export function getAuditActorSecondary(log) {
  if (!log?.actor?.username) {
    return "";
  }

  const primary = getAuditActorPrimary(log);
  return primary !== log.actor.username ? log.actor.username : "";
}

export function normalizeAuditValue(key, value) {
  if (isEmptyValue(value)) {
    return { kind: "empty", text: "—" };
  }

  if (Array.isArray(value)) {
    return {
      kind: "list",
      items: value.map((item, index) => ({
        id: `${key}-${index}`,
        label: Array.isArray(item) || typeof item !== "object" || item === null ? null : `عنصر ${index + 1}`,
        value: normalizeAuditValue(key, item),
      })),
    };
  }

  if (typeof value === "object") {
    const items = Object.entries(value)
      .filter(([, nestedValue]) => !isEmptyValue(nestedValue))
      .map(([nestedKey, nestedValue]) => ({
        key: nestedKey,
        label: getAuditFieldLabel(nestedKey),
        value: normalizeAuditValue(nestedKey, nestedValue),
      }));

    return items.length ? { kind: "pairs", items } : { kind: "empty", text: "—" };
  }

  return { kind: "text", text: scalarToText(key, value) };
}

export function auditValueToPlainText(normalizedValue) {
  if (!normalizedValue) {
    return "—";
  }

  if (normalizedValue.kind === "text" || normalizedValue.kind === "empty") {
    return normalizedValue.text;
  }

  if (normalizedValue.kind === "list") {
    return normalizedValue.items
      .map((item) => auditValueToPlainText(item.value))
      .filter(Boolean)
      .join("، ");
  }

  if (normalizedValue.kind === "pairs") {
    return normalizedValue.items
      .map((item) => `${item.label}: ${auditValueToPlainText(item.value)}`)
      .join("، ");
  }

  return "—";
}

export function getAuditNarratives(log) {
  const oldValues = log?.old_values || {};
  const newValues = log?.new_values || {};
  const items = [];
  const message = newValues.message || oldValues.message;
  const rejectionReason = newValues.rejection_reason || oldValues.rejection_reason;

  if (typeof message === "string" && message.trim()) {
    items.push({
      key: "message",
      title: "ملاحظة العملية",
      tone: "neutral",
      body: message.trim(),
    });
  }

  if (typeof rejectionReason === "string" && rejectionReason.trim()) {
    items.push({
      key: "rejection_reason",
      title: "سبب الرفض",
      tone: "attention",
      body: rejectionReason.trim(),
    });
  }

  return items;
}

export function getAuditChangeEntries(log) {
  const oldValues = log?.old_values || {};
  const newValues = log?.new_values || {};
  const keys = Array.from(new Set([...Object.keys(oldValues), ...Object.keys(newValues)]));

  return keys
    .filter((key) => !HIDDEN_CHANGE_KEYS.has(key))
    .map((key) => {
      const beforeValue = oldValues[key];
      const afterValue = newValues[key];
      const beforeNormalized = normalizeAuditValue(key, beforeValue);
      const afterNormalized = normalizeAuditValue(key, afterValue);
      const beforeEmpty = isEmptyValue(beforeValue);
      const afterEmpty = isEmptyValue(afterValue);
      let changeType = "same";

      if (beforeEmpty && !afterEmpty) {
        changeType = "added";
      } else if (!beforeEmpty && afterEmpty) {
        changeType = "removed";
      } else if (comparableValue(beforeValue) !== comparableValue(afterValue)) {
        changeType = "changed";
      }

      return {
        key,
        label: getAuditFieldLabel(key),
        changeType,
        before: beforeNormalized,
        after: afterNormalized,
      };
    })
    .filter((entry) => entry.changeType !== "same");
}

export function getAuditDisplaySummary(log) {
  const narratives = getAuditNarratives(log);
  if (narratives.length) {
    return narratives[0].body;
  }

  const changes = getAuditChangeEntries(log);
  const statusChange = changes.find((entry) => entry.key === "status");
  if (statusChange) {
    return `تغيّرت الحالة من ${auditValueToPlainText(statusChange.before)} إلى ${auditValueToPlainText(statusChange.after)}.`;
  }

  if (changes.length === 1) {
    return `تم تحديث ${changes[0].label}.`;
  }

  if (changes.length > 1) {
    return `تم تحديث ${changes.length} حقول مرتبطة بهذه العملية.`;
  }

  if (log?.entity_display) {
    return `العملية مرتبطة بـ ${log.entity_display}.`;
  }

  return log?.change_summary || getAuditEventTitle(log);
}
