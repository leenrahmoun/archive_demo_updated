import { useCallback, useEffect, useState } from "react";
import {
  createManagedDocumentType,
  deleteManagedDocumentType,
  getManagedDocumentTypes,
  setManagedDocumentTypeActiveState,
  updateManagedDocumentType,
} from "../api/documentTypesApi";
import { useAuth } from "../auth/useAuth";
import { AlertMessage } from "../components/AlertMessage";
import { PageHeader } from "../components/PageHeader";
import { PaginationControls } from "../components/PaginationControls";
import { EmptyBlock, LoadingBlock } from "../components/StateBlock";

function createEmptyForm() {
  return {
    name: "",
    is_active: true,
  };
}

function buildEditForm(documentType) {
  return {
    name: documentType.name || "",
    is_active: Boolean(documentType.is_active),
  };
}

function getApiErrorMessage(error, fallbackMessage) {
  const responseData = error?.response?.data;

  if (!responseData) {
    return fallbackMessage;
  }

  if (typeof responseData.detail === "string") {
    return responseData.detail;
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
      const [, value] = firstFieldWithError;
      return Array.isArray(value) ? value[0] : value;
    }
  }

  return fallbackMessage;
}

function formatDateTime(value) {
  if (!value) {
    return "غير متوفر";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("ar");
}

function DocumentTypeEditorForm({
  mode,
  form,
  isSubmitting,
  errorMessage,
  onChange,
  onSubmit,
  onCancel,
}) {
  const isEditMode = mode === "edit";

  return (
    <form className="document-type-editor-form" onSubmit={onSubmit}>
      <AlertMessage type="error" message={errorMessage} />

      <div className="form-grid">
        <label className="form-field full-row">
          <span>اسم نوع الوثيقة</span>
          <input
            type="text"
            name="name"
            value={form.name}
            onChange={onChange}
            placeholder="مثال: بيان خدمة"
            autoComplete="off"
            required
          />
          <small className="muted">سيظهر هذا الاسم مباشرة في قوائم اختيار نوع الوثيقة للمستخدمين.</small>
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
      </div>

      <div className="user-editor-actions">
        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "جارٍ الحفظ..." : isEditMode ? "حفظ التعديلات" : "إضافة النوع"}
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

export function DocumentTypesManagementPage() {
  const { user } = useAuth();
  const [documentTypes, setDocumentTypes] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreateSubmitting, setIsCreateSubmitting] = useState(false);
  const [isEditSubmitting, setIsEditSubmitting] = useState(false);
  const [isActionSubmitting, setIsActionSubmitting] = useState(false);
  const [pageError, setPageError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [createError, setCreateError] = useState("");
  const [editError, setEditError] = useState("");
  const [createForm, setCreateForm] = useState(createEmptyForm());
  const [editingType, setEditingType] = useState(null);
  const [editForm, setEditForm] = useState(createEmptyForm());
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [count, setCount] = useState(0);
  const [hasNextPage, setHasNextPage] = useState(false);
  const [hasPreviousPage, setHasPreviousPage] = useState(false);
  const [pageSizeHint, setPageSizeHint] = useState(1);

  const loadDocumentTypes = useCallback(async (targetPage, showLoadingState = false) => {
    if (showLoadingState) {
      setIsLoading(true);
    }

    try {
      const params = {
        page: targetPage,
        ordering: "name",
      };

      if (searchQuery.trim()) {
        params.search = searchQuery.trim();
      }

      if (statusFilter === "active") {
        params.is_active = true;
      } else if (statusFilter === "inactive") {
        params.is_active = false;
      }

      const response = await getManagedDocumentTypes(params);
      const currentResults = response.results || [];
      setDocumentTypes(response.results || []);
      setCount(response.count || 0);
      setHasNextPage(Boolean(response.next));
      setHasPreviousPage(Boolean(response.previous));
      if (currentResults.length) {
        setPageSizeHint((current) => Math.max(current, currentResults.length));
      }
      setPageError("");
      return response;
    } catch (error) {
      setPageError(getApiErrorMessage(error, "تعذر تحميل أنواع الوثائق."));
      return null;
    } finally {
      if (showLoadingState) {
        setIsLoading(false);
      }
    }
  }, [searchQuery, statusFilter]);

  useEffect(() => {
    if (!user || user.role !== "admin") {
      return;
    }

    loadDocumentTypes(page, true);
  }, [loadDocumentTypes, page, user]);

  function handleFormChange(setForm, setError) {
    return (event) => {
      const { name, type, checked, value } = event.target;
      setError("");
      setSuccessMessage("");
      setForm((current) => ({
        ...current,
        [name]: type === "checkbox" ? checked : value,
      }));
    };
  }

  async function handleCreateSubmit(event) {
    event.preventDefault();
    setCreateError("");
    setPageError("");
    setSuccessMessage("");
    setIsCreateSubmitting(true);

    try {
      await createManagedDocumentType({
        name: createForm.name.trim(),
        is_active: createForm.is_active,
      });
      setCreateForm(createEmptyForm());
      setPage(1);
      await loadDocumentTypes(1, false);
      setSuccessMessage("تمت إضافة نوع الوثيقة بنجاح.");
    } catch (error) {
      setCreateError(getApiErrorMessage(error, "تعذر إضافة نوع الوثيقة."));
    } finally {
      setIsCreateSubmitting(false);
    }
  }

  function handleStartEdit(documentType) {
    setEditingType(documentType);
    setEditForm(buildEditForm(documentType));
    setEditError("");
    setSuccessMessage("");
  }

  function handleCloseEdit() {
    setEditingType(null);
    setEditForm(createEmptyForm());
    setEditError("");
  }

  async function handleEditSubmit(event) {
    event.preventDefault();
    if (!editingType) {
      return;
    }

    setEditError("");
    setPageError("");
    setSuccessMessage("");
    setIsEditSubmitting(true);

    try {
      await updateManagedDocumentType(editingType.id, {
        name: editForm.name.trim(),
        is_active: editForm.is_active,
      });
      await loadDocumentTypes(page, false);
      handleCloseEdit();
      setSuccessMessage("تم تحديث نوع الوثيقة بنجاح.");
    } catch (error) {
      setEditError(getApiErrorMessage(error, "تعذر تحديث نوع الوثيقة."));
    } finally {
      setIsEditSubmitting(false);
    }
  }

  async function handleToggleActive(documentType) {
    const nextIsActive = !documentType.is_active;
    const confirmed = window.confirm(
      nextIsActive
        ? `هل تريد إعادة تفعيل النوع ${documentType.name}؟`
        : `هل تريد تعطيل النوع ${documentType.name}؟`
    );
    if (!confirmed) {
      return;
    }

    setPageError("");
    setSuccessMessage("");
    setIsActionSubmitting(true);
    try {
      await setManagedDocumentTypeActiveState(documentType.id, nextIsActive);
      await loadDocumentTypes(page, false);
      setSuccessMessage(nextIsActive ? "تم تفعيل نوع الوثيقة." : "تم تعطيل نوع الوثيقة.");
    } catch (error) {
      setPageError(
        getApiErrorMessage(
          error,
          nextIsActive ? "تعذر تفعيل نوع الوثيقة." : "تعذر تعطيل نوع الوثيقة."
        )
      );
    } finally {
      setIsActionSubmitting(false);
    }
  }

  async function handleDelete(documentType) {
    const confirmed = window.confirm(`هل تريد حذف النوع ${documentType.name} نهائيًا؟`);
    if (!confirmed) {
      return;
    }

    setPageError("");
    setSuccessMessage("");
    setIsActionSubmitting(true);

    try {
      await deleteManagedDocumentType(documentType.id);
      const targetPage = documentTypes.length === 1 && page > 1 ? page - 1 : page;
      await loadDocumentTypes(targetPage, false);
      if (targetPage !== page) {
        setPage(targetPage);
      }
      setSuccessMessage("تم حذف نوع الوثيقة بنجاح.");
    } catch (error) {
      setPageError(getApiErrorMessage(error, "تعذر حذف نوع الوثيقة."));
    } finally {
      setIsActionSubmitting(false);
    }
  }

  function handleSearchSubmit(event) {
    event.preventDefault();
    setPage(1);
    setSearchQuery(searchInput);
  }

  const totalPages = Math.max(1, Math.ceil(count / pageSizeHint));

  if (user?.role !== "admin") {
    return (
      <section>
        <PageHeader title="إدارة أنواع الوثائق" />
        <div className="card">
          <p>هذه الصفحة مخصصة للمدير فقط.</p>
        </div>
      </section>
    );
  }

  return (
    <section>
      <PageHeader
        title="إدارة أنواع الوثائق"
        subtitle="إضافة الأنواع الجديدة، تعديل الأسماء، وتعطيل الأنواع المستخدمة من لوحة إدارة واحدة."
      />

      <AlertMessage type="success" message={successMessage} />
      <AlertMessage type="error" message={pageError} />

      <div className="user-management-grid">
        <div className="card">
          <div className="control-panel-card__header">
            <div>
              <h3>إضافة نوع جديد</h3>
              <p className="muted">سيظهر النوع النشط مباشرة في نماذج إنشاء وتعديل الوثائق.</p>
            </div>
          </div>

          <DocumentTypeEditorForm
            mode="create"
            form={createForm}
            isSubmitting={isCreateSubmitting}
            errorMessage={createError}
            onChange={handleFormChange(setCreateForm, setCreateError)}
            onSubmit={handleCreateSubmit}
          />
        </div>

        <div className="card control-panel-card--accent">
          <div className="control-panel-card__header">
            <div>
              <h3>كيف تعمل القائمة الآن؟</h3>
              <p className="muted">القوائم العامة تعرض الأنواع النشطة فقط، بينما تبقى الأنواع غير النشطة ظاهرة داخل الوثائق القديمة المرتبطة بها.</p>
            </div>
          </div>

          <div className="control-panel-rules">
            <p>
              يمكن <strong>حذف</strong> النوع إذا لم يُستخدم في أي وثيقة بعد.
            </p>
            <p>
              إذا كان النوع مستخدمًا سابقًا، فيمكن <strong>تعطيله</strong> بدلًا من حذفه حتى لا يتأثر السجل التاريخي للوثائق.
            </p>
            <p>
              يتم منع تكرار الأسماء المتشابهة حتى لو اختلفت المسافات أو بعض أشكال الحروف العربية.
            </p>
            <div className="control-panel-rules__meta">
              <span>إجمالي الأنواع: {count}</span>
              <span>المعروض الآن: {documentTypes.length}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="control-panel-card__header">
          <div>
            <h3>قائمة أنواع الوثائق</h3>
            <p className="muted">ابحث بالاسم، ثم عدّل أو عطّل أو احذف النوع حسب حالته واستخدامه.</p>
          </div>
        </div>

        <form className="filters-grid document-types-toolbar" onSubmit={handleSearchSubmit}>
          <label className="form-field full-row">
            <span>بحث بالاسم</span>
            <input
              type="text"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="اكتب جزءًا من اسم النوع"
              aria-label="بحث أنواع الوثائق"
            />
          </label>

          <label className="form-field">
            <span>الحالة</span>
            <select
              value={statusFilter}
              onChange={(event) => {
                setStatusFilter(event.target.value);
                setPage(1);
              }}
            >
              <option value="all">الكل</option>
              <option value="active">النشطة فقط</option>
              <option value="inactive">غير النشطة فقط</option>
            </select>
          </label>

          <div className="document-types-toolbar__actions">
            <button type="submit">بحث</button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setSearchInput("");
                setSearchQuery("");
                setStatusFilter("all");
                setPage(1);
              }}
            >
              إعادة ضبط
            </button>
          </div>
        </form>

        {isLoading ? (
          <LoadingBlock />
        ) : documentTypes.length ? (
          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>اسم النوع</th>
                  <th>الحالة</th>
                  <th>الاستخدام</th>
                  <th>آخر تحديث</th>
                  <th>الإجراءات</th>
                </tr>
              </thead>
              <tbody>
                {documentTypes.map((documentType) => (
                  <tr key={documentType.id}>
                    <td>
                      <div className="document-type-name-cell">
                        <strong>{documentType.name}</strong>
                        <span className="muted">أضيف في {formatDateTime(documentType.created_at)}</span>
                      </div>
                    </td>
                    <td>
                      <span className={`state-pill ${documentType.is_active ? "state-pill--active" : "state-pill--inactive"}`}>
                        {documentType.is_active ? "نشط" : "غير نشط"}
                      </span>
                    </td>
                    <td>
                      <span className={`document-type-usage ${documentType.is_used ? "document-type-usage--used" : "document-type-usage--unused"}`}>
                        {documentType.is_used
                          ? `مستخدم في ${documentType.documents_count} وثيقة`
                          : "غير مستخدم بعد"}
                      </span>
                    </td>
                    <td>{formatDateTime(documentType.updated_at)}</td>
                    <td>
                      <div className="user-actions">
                        <button type="button" className="btn-secondary" onClick={() => handleStartEdit(documentType)}>
                          تعديل
                        </button>
                        {documentType.is_used ? (
                          <button
                            type="button"
                            className={documentType.is_active ? "btn-warning" : "btn-secondary"}
                            onClick={() => handleToggleActive(documentType)}
                            disabled={isActionSubmitting}
                          >
                            {documentType.is_active ? "تعطيل" : "تفعيل"}
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="btn-danger"
                            onClick={() => handleDelete(documentType)}
                            disabled={isActionSubmitting}
                          >
                            حذف
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyBlock message="لا توجد أنواع وثائق مطابقة للبحث الحالي." />
        )}
      </div>

      <PaginationControls
        page={page}
        totalPages={totalPages}
        hasPrevious={hasPreviousPage}
        hasNext={hasNextPage}
        onPrevious={() => setPage((current) => Math.max(1, current - 1))}
        onNext={() => setPage((current) => current + 1)}
      />

      {editingType ? (
        <div className="modal-backdrop" onClick={handleCloseEdit}>
          <div
            className="modal-card"
            onClick={(event) => {
              event.stopPropagation();
            }}
          >
            <div className="control-panel-card__header">
              <div>
                <h3>تعديل نوع الوثيقة</h3>
                <p className="muted">يمكنك تعديل الاسم أو تغيير الحالة من دون التأثير على الوثائق القديمة المرتبطة بهذا النوع.</p>
              </div>
              <button type="button" className="btn-secondary" onClick={handleCloseEdit}>
                إغلاق
              </button>
            </div>

            <DocumentTypeEditorForm
              mode="edit"
              form={editForm}
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
