import { useCallback, useEffect, useState } from "react";
import { createUser, deleteUser, getUsers, updateUser } from "../api/usersApi";
import { useAuth } from "../auth/useAuth";
import { AlertMessage } from "../components/AlertMessage";
import { PageHeader } from "../components/PageHeader";
import { PaginationControls } from "../components/PaginationControls";
import { EmptyBlock, LoadingBlock } from "../components/StateBlock";

const ROLE_OPTIONS = [
  { value: "admin", label: "مدير" },
  { value: "auditor", label: "مدقق" },
  { value: "data_entry", label: "مدخل بيانات" },
  { value: "reader", label: "قارئ" },
];

const FIELD_LABELS = {
  username: "اسم المستخدم",
  password: "كلمة المرور",
  role: "الدور",
  is_active: "الحالة",
  assigned_auditor_id: "المدقق المرتبط",
  first_name: "الاسم الأول",
  last_name: "اسم العائلة",
  email: "البريد الإلكتروني",
};

const USERS_PAGE_SIZE = 25;
const AUDITORS_PAGE_SIZE = 200;

function createEmptyForm(defaultAuditorId = "") {
  return {
    username: "",
    password: "",
    first_name: "",
    last_name: "",
    email: "",
    role: "data_entry",
    is_active: true,
    assigned_auditor_id: defaultAuditorId ? String(defaultAuditorId) : "",
  };
}

function buildEditForm(userRecord) {
  return {
    username: userRecord.username || "",
    password: "",
    first_name: userRecord.first_name || "",
    last_name: userRecord.last_name || "",
    email: userRecord.email || "",
    role: userRecord.role || "data_entry",
    is_active: Boolean(userRecord.is_active),
    assigned_auditor_id: userRecord.assigned_auditor_id ? String(userRecord.assigned_auditor_id) : "",
  };
}

function syncFormWithAuditors(form, auditors, useDefaultAuditor) {
  if (form.role !== "data_entry") {
    return { ...form, assigned_auditor_id: "" };
  }

  const hasSelectedAuditor = auditors.some((auditor) => String(auditor.id) === String(form.assigned_auditor_id));
  if (hasSelectedAuditor) {
    return form;
  }

  if (useDefaultAuditor && auditors.length) {
    return { ...form, assigned_auditor_id: String(auditors[0].id) };
  }

  return { ...form, assigned_auditor_id: "" };
}

function getApiErrorMessage(error, fallbackMessage) {
  const responseData = error?.response?.data;

  if (!responseData) {
    return fallbackMessage;
  }

  if (typeof responseData.detail === "string") {
    return responseData.detail;
  }

  if (Array.isArray(responseData.non_field_errors) && responseData.non_field_errors.length) {
    return responseData.non_field_errors[0];
  }

  if (typeof responseData === "string") {
    return responseData;
  }

  if (typeof responseData === "object") {
    const firstFieldWithError = Object.entries(responseData).find(([, value]) => {
      if (Array.isArray(value)) {
        return value.length > 0;
      }
      return Boolean(value);
    });

    if (firstFieldWithError) {
      const [field, value] = firstFieldWithError;
      const fieldLabel = FIELD_LABELS[field] || field;
      const message = Array.isArray(value) ? value[0] : value;
      return `${fieldLabel}: ${message}`;
    }
  }

  return fallbackMessage;
}

function getRoleLabel(role) {
  return ROLE_OPTIONS.find((option) => option.value === role)?.label || role;
}

function getAssignedAuditorLabel(userRecord) {
  const assignedAuditor = userRecord.assigned_auditor;
  if (!assignedAuditor && !userRecord.assigned_auditor_username) {
    return userRecord.role === "data_entry" ? "غير محدد" : "غير مطلوب";
  }

  if (!assignedAuditor) {
    return userRecord.assigned_auditor_username;
  }

  if (assignedAuditor.full_name) {
    return `${assignedAuditor.full_name} (${assignedAuditor.username})`;
  }

  return assignedAuditor.username;
}

function UserEditorForm({
  mode,
  form,
  auditors,
  isSubmitting,
  errorMessage,
  onChange,
  onSubmit,
  onCancel,
}) {
  const isEditMode = mode === "edit";
  const isDataEntry = form.role === "data_entry";
  const hasAuditors = auditors.length > 0;
  const isAssignmentBlocked = isDataEntry && !hasAuditors;

  return (
    <form className="user-editor-form" onSubmit={onSubmit}>
      <AlertMessage type="error" message={errorMessage} />

      <div className="form-grid">
        <label className="form-field">
          <span>اسم المستخدم</span>
          <input
            type="text"
            name="username"
            value={form.username}
            onChange={onChange}
            placeholder="مثال: data_entry_01"
            autoComplete="off"
            required
          />
        </label>

        <label className="form-field">
          <span>{isEditMode ? "كلمة المرور الجديدة" : "كلمة المرور"}</span>
          <input
            type="password"
            name="password"
            value={form.password}
            onChange={onChange}
            placeholder={isEditMode ? "اترك الحقل فارغًا بدون تغيير" : "أدخل كلمة مرور أولية"}
            autoComplete={isEditMode ? "new-password" : "off"}
            required={!isEditMode}
          />
        </label>

        <label className="form-field">
          <span>الدور</span>
          <select name="role" value={form.role} onChange={onChange}>
            {ROLE_OPTIONS.map((role) => (
              <option key={role.value} value={role.value}>
                {role.label}
              </option>
            ))}
          </select>
        </label>

        <label className="form-field form-field--checkbox">
          <span>الحالة</span>
          <span className="checkbox-row">
            <input
              type="checkbox"
              name="is_active"
              checked={form.is_active}
              onChange={onChange}
            />
            <span>{form.is_active ? "نشط" : "غير نشط"}</span>
          </span>
        </label>

        {isDataEntry ? (
          <label className="form-field full-row">
            <span>المدقق المرتبط</span>
            <select
              name="assigned_auditor_id"
              value={form.assigned_auditor_id}
              onChange={onChange}
              disabled={!hasAuditors}
              required
            >
              <option value="" disabled>
                {hasAuditors ? "اختر مدققًا" : "لا يوجد مدققون متاحون"}
              </option>
              {auditors.map((auditor) => (
                <option key={auditor.id} value={auditor.id}>
                  {auditor.full_name ? `${auditor.full_name} (${auditor.username})` : auditor.username}
                </option>
              ))}
            </select>
            <small className="muted">
              {hasAuditors
                ? "سيظهر هذا المدخل فقط في قائمة المراجعة الخاص بالمدقق المحدد."
                : "أنشئ مستخدمًا بدور مدقق أولًا قبل إضافة مدخل بيانات جديد."}
            </small>
          </label>
        ) : null}
      </div>

      <div className="user-editor-actions">
        <button type="submit" disabled={isSubmitting || isAssignmentBlocked}>
          {isSubmitting ? "جارٍ الحفظ..." : isEditMode ? "حفظ التغييرات" : "إنشاء المستخدم"}
        </button>
        {onCancel ? (
          <button type="button" className="btn-secondary" onClick={onCancel} disabled={isSubmitting}>
            إلغاء
          </button>
        ) : null}
      </div>
    </form>
  );
}

export function UserManagementPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [auditors, setAuditors] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreateSubmitting, setIsCreateSubmitting] = useState(false);
  const [isEditSubmitting, setIsEditSubmitting] = useState(false);
  const [isDeleteSubmitting, setIsDeleteSubmitting] = useState(false);
  const [pageError, setPageError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [createError, setCreateError] = useState("");
  const [editError, setEditError] = useState("");
  const [createForm, setCreateForm] = useState(createEmptyForm());
  const [editingUser, setEditingUser] = useState(null);
  const [editForm, setEditForm] = useState(createEmptyForm());
  const [page, setPage] = useState(1);
  const [count, setCount] = useState(0);
  const [hasNextPage, setHasNextPage] = useState(false);
  const [hasPreviousPage, setHasPreviousPage] = useState(false);

  const loadControlPanel = useCallback(async (targetPage, showLoadingState = false) => {
    if (showLoadingState) {
      setIsLoading(true);
    }

    try {
      const [usersResponse, auditorsResponse] = await Promise.all([
        getUsers({
          page: targetPage,
          page_size: USERS_PAGE_SIZE,
          ordering: "username",
        }),
        getUsers({
          role: "auditor",
          page_size: AUDITORS_PAGE_SIZE,
          ordering: "username",
        }),
      ]);

      const fetchedUsers = usersResponse.results || [];
      const fetchedAuditors = auditorsResponse.results || [];

      setUsers(fetchedUsers);
      setAuditors(fetchedAuditors);
      setCount(usersResponse.count || 0);
      setHasNextPage(Boolean(usersResponse.next));
      setHasPreviousPage(Boolean(usersResponse.previous));
      setPageError("");
      setCreateForm((current) => syncFormWithAuditors(current, fetchedAuditors, true));
      setEditForm((current) => syncFormWithAuditors(current, fetchedAuditors, false));
      return { fetchedUsers, fetchedAuditors, usersResponse };
    } catch (error) {
      setPageError(getApiErrorMessage(error, "تعذر تحميل لوحة إدارة المستخدمين."));
      return null;
    } finally {
      if (showLoadingState) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!user || user.role !== "admin") {
      return;
    }

    loadControlPanel(page, true);
  }, [loadControlPanel, page, user]);

  function handleFormChange(setForm, setError) {
    return (event) => {
      const { name, type, checked, value } = event.target;
      const nextValue = type === "checkbox" ? checked : value;

      setError("");
      setSuccessMessage("");
      setForm((current) => {
        const nextForm = {
          ...current,
          [name]: nextValue,
        };

        if (name === "role" && nextValue !== "data_entry") {
          nextForm.assigned_auditor_id = "";
        }

        if (
          name === "role" &&
          nextValue === "data_entry" &&
          !current.assigned_auditor_id &&
          auditors.length
        ) {
          nextForm.assigned_auditor_id = String(auditors[0].id);
        }

        return nextForm;
      });
    };
  }

  function buildPayload(form) {
    const payload = {
      username: form.username.trim(),
      first_name: form.first_name,
      last_name: form.last_name,
      email: form.email,
      role: form.role,
      is_active: form.is_active,
      assigned_auditor_id: form.role === "data_entry" && form.assigned_auditor_id ? Number(form.assigned_auditor_id) : null,
    };

    if (form.password.trim()) {
      payload.password = form.password.trim();
    }

    return payload;
  }

  async function handleCreateSubmit(event) {
    event.preventDefault();
    setCreateError("");
    setPageError("");
    setSuccessMessage("");

    if (createForm.role === "data_entry" && !createForm.assigned_auditor_id) {
      setCreateError("يجب ربط مدخل البيانات بمدقق محدد قبل الحفظ.");
      return;
    }

    setIsCreateSubmitting(true);
    try {
      await createUser(buildPayload(createForm));
      const refreshedData = await loadControlPanel(1, false);
      setPage(1);
      setCreateForm(createEmptyForm(refreshedData?.fetchedAuditors?.[0]?.id || ""));
      setSuccessMessage("تم إنشاء المستخدم وربط صلاحياته بنجاح.");
    } catch (error) {
      setCreateError(getApiErrorMessage(error, "تعذر إنشاء المستخدم."));
    } finally {
      setIsCreateSubmitting(false);
    }
  }

  function handleStartEdit(userRecord) {
    setEditingUser(userRecord);
    setEditForm(syncFormWithAuditors(buildEditForm(userRecord), auditors, false));
    setEditError("");
    setSuccessMessage("");
  }

  function handleCloseEdit() {
    setEditingUser(null);
    setEditForm(createEmptyForm());
    setEditError("");
  }

  async function handleEditSubmit(event) {
    event.preventDefault();
    if (!editingUser) {
      return;
    }

    setEditError("");
    setPageError("");
    setSuccessMessage("");

    if (editForm.role === "data_entry" && !editForm.assigned_auditor_id) {
      setEditError("يجب ربط مدخل البيانات بمدقق محدد قبل الحفظ.");
      return;
    }

    setIsEditSubmitting(true);
    try {
      await updateUser(editingUser.id, buildPayload(editForm));
      await loadControlPanel(page, false);
      handleCloseEdit();
      setSuccessMessage("تم تحديث بيانات المستخدم وربط المراجعة بنجاح.");
    } catch (error) {
      setEditError(getApiErrorMessage(error, "تعذر تحديث المستخدم."));
    } finally {
      setIsEditSubmitting(false);
    }
  }

  async function handleDelete(userRecord) {
    const confirmed = window.confirm(`هل تريد حذف المستخدم ${userRecord.username}؟`);
    if (!confirmed) {
      return;
    }

    setPageError("");
    setSuccessMessage("");
    setIsDeleteSubmitting(true);

    try {
      await deleteUser(userRecord.id);
      const targetPage = users.length === 1 && page > 1 ? page - 1 : page;
      await loadControlPanel(targetPage, false);
      if (targetPage !== page) {
        setPage(targetPage);
      }
      if (editingUser?.id === userRecord.id) {
        handleCloseEdit();
      }
      setSuccessMessage("تم حذف المستخدم بنجاح.");
    } catch (error) {
      setPageError(getApiErrorMessage(error, "تعذر حذف المستخدم."));
    } finally {
      setIsDeleteSubmitting(false);
    }
  }

  const totalPages = Math.max(1, Math.ceil(count / USERS_PAGE_SIZE));

  if (user?.role !== "admin") {
    return (
      <section>
        <PageHeader title="لوحة إدارة المستخدمين" />
        <div className="card">
          <p>هذه الصفحة مخصصة للمدير فقط.</p>
        </div>
      </section>
    );
  }

  return (
    <section>
      <PageHeader
        title="لوحة إدارة المستخدمين"
        subtitle="إنشاء الحسابات، تعديل الأدوار، وربط كل مدخل بيانات بالمدقق المسؤول عنه من مكان واحد."
      />

      <AlertMessage type="success" message={successMessage} />
      <AlertMessage type="error" message={pageError} />

      <div className="user-management-grid">
        <div className="card">
          <div className="control-panel-card__header">
            <div>
              <h3>إنشاء مستخدم جديد</h3>
              <p className="muted">كلمة المرور مطلوبة عند الإنشاء، وربط المدقق يظهر فقط لمدخل البيانات.</p>
            </div>
          </div>

          <UserEditorForm
            mode="create"
            form={createForm}
            auditors={auditors}
            isSubmitting={isCreateSubmitting}
            errorMessage={createError}
            onChange={handleFormChange(setCreateForm, setCreateError)}
            onSubmit={handleCreateSubmit}
          />
        </div>

        <div className="card control-panel-card--accent">
          <div className="control-panel-card__header">
            <div>
              <h3>قواعد التوزيع الحالية</h3>
              <p className="muted">الرؤية في قائمة المراجعة تعتمد مباشرة على هذا الربط.</p>
            </div>
          </div>

          <div className="control-panel-rules">
            <p>
              يرى <strong>المدقق</strong> فقط الوثائق الخاصة بمدخلي البيانات المرتبطين به.
            </p>
            <p>
              يرى <strong>المدير</strong> جميع عناصر القائمة ويمكنه إدارة المستخدمين والأدوار بالكامل.
            </p>
            <p>
              يبقى <strong>القارئ</strong> للعرض فقط، ولا يحصل أي مستخدم غير مدير على صفحة الإدارة.
            </p>
            <div className="control-panel-rules__meta">
              <span>عدد المدققين المتاحين الآن: {auditors.length}</span>
              <span>إجمالي المستخدمين: {count}</span>
            </div>
          </div>
        </div>
      </div>

      {isLoading ? (
        <LoadingBlock />
      ) : (
        <div className="card">
          <div className="control-panel-card__header">
            <div>
              <h3>المستخدمون</h3>
              <p className="muted">عرض الحالة الحالية للمستخدمين وربط مدخلي البيانات بالمدققين.</p>
            </div>
          </div>

          {users.length ? (
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>اسم المستخدم</th>
                    <th>الدور</th>
                    <th>الحالة</th>
                    <th>المدقق المرتبط</th>
                    <th>الإجراءات</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((userRecord) => (
                    <tr key={userRecord.id}>
                      <td>
                        <div className="user-cell">
                          <strong>{userRecord.username}</strong>
                          <span className="muted">
                            {userRecord.full_name || "لا يوجد اسم مسجل"}
                          </span>
                        </div>
                      </td>
                      <td>
                        <span className={`role-chip role-chip--${userRecord.role}`}>
                          {getRoleLabel(userRecord.role)}
                        </span>
                      </td>
                      <td>
                        <span className={`state-pill ${userRecord.is_active ? "state-pill--active" : "state-pill--inactive"}`}>
                          {userRecord.is_active ? "نشط" : "غير نشط"}
                        </span>
                      </td>
                      <td>{getAssignedAuditorLabel(userRecord)}</td>
                      <td>
                        <div className="user-actions">
                          <button type="button" className="btn-secondary" onClick={() => handleStartEdit(userRecord)}>
                            تعديل
                          </button>
                          <button
                            type="button"
                            className="btn-danger"
                            onClick={() => handleDelete(userRecord)}
                            disabled={isDeleteSubmitting}
                          >
                            حذف
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyBlock message="لا توجد حسابات مطابقة حتى الآن." />
          )}
        </div>
      )}

      <PaginationControls
        page={page}
        totalPages={totalPages}
        hasPrevious={hasPreviousPage}
        hasNext={hasNextPage}
        onPrevious={() => {
          setPage((current) => Math.max(1, current - 1));
        }}
        onNext={() => {
          setPage((current) => current + 1);
        }}
      />

      {editingUser ? (
        <div className="modal-backdrop" onClick={handleCloseEdit}>
          <div
            className="modal-card"
            onClick={(event) => {
              event.stopPropagation();
            }}
          >
            <div className="control-panel-card__header">
              <div>
                <h3>تعديل المستخدم</h3>
                <p className="muted">يمكنك تغيير الدور أو تحديث كلمة المرور أو تعديل ربط المدقق.</p>
              </div>
              <button type="button" className="btn-secondary" onClick={handleCloseEdit}>
                إغلاق
              </button>
            </div>

            <UserEditorForm
              mode="edit"
              form={editForm}
              auditors={auditors}
              isSubmitting={isEditSubmitting}
              errorMessage={editError}
              onChange={handleFormChange(setEditForm, setEditError)}
              onSubmit={handleEditSubmit}
              onCancel={handleCloseEdit}
            />
          </div>
        </div>
      ) : null}
    </section>
  );
}
