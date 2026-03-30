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

const DEFAULT_PAGE_SIZE = 20;

function createEmptyForm() {
  return {
    name: "",
    is_active: true,
  };
}

function createDefaultFilters() {
  return {
    search: "",
    status: "all",
  };
}

function buildAppliedFilters(draftFilters) {
  return {
    search: draftFilters.search.trim(),
    status: draftFilters.status,
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

function formatUsageLabel(usageCount) {
  if (!usageCount) {
    return "غير مستخدم بعد";
  }

  return `عدد الوثائق المرتبطة: ${usageCount}`;
}

function getCreateSuccessMessage(isActive) {
  if (isActive) {
    return "تمت إضافة نوع الوثيقة بنجاح، وسيظهر فورًا في القوائم العامة والنماذج الجديدة.";
  }

  return "تمت إضافة نوع الوثيقة كنوع غير نشط. لن يظهر في القوائم العامة حتى يتم تفعيله.";
}

function getUpdateSuccessMessage(previousType, nextValues) {
  const nameChanged = nextValues.name !== previousType.name;
  const deactivated = previousType.is_active && !nextValues.is_active;
  const activated = !previousType.is_active && nextValues.is_active;

  if (nameChanged && deactivated) {
    return "تم تحديث اسم نوع الوثيقة وتعطيله. سيبقى الاسم ظاهرًا في الوثائق المرتبطة به.";
  }

  if (nameChanged && activated) {
    return "تم تحديث اسم نوع الوثيقة وإعادة تفعيله بنجاح.";
  }

  if (deactivated) {
    return "تم تعطيل نوع الوثيقة. لن يظهر بعد الآن في القوائم العامة أو النماذج الجديدة.";
  }

  if (activated) {
    return "تمت إعادة تفعيل نوع الوثيقة، وسيظهر مجددًا في القوائم العامة والنماذج الجديدة.";
  }

  if (nameChanged) {
    return "تم تحديث اسم نوع الوثيقة بنجاح.";
  }

  return "تم حفظ نوع الوثيقة بنجاح.";
}

function getDeactivateConfirmationMessage(documentType) {
  const usageNote = documentType.usage_count
    ? `سيختفي هذا النوع من القوائم العامة والنماذج الجديدة، لكن اسمه سيبقى ظاهرًا داخل ${documentType.usage_count} وثيقة مرتبطة به.`
    : "سيختفي هذا النوع من القوائم العامة والنماذج الجديدة، ويمكنك إعادة تفعيله لاحقًا عند الحاجة.";

  return `هل تريد تعطيل النوع «${documentType.name}»؟ ${usageNote}`;
}

function getReactivateConfirmationMessage(documentType) {
  return `هل تريد إعادة تفعيل النوع «${documentType.name}»؟ سيظهر مرة أخرى في القوائم العامة والنماذج الجديدة.`;
}

function getDeleteConfirmationMessage(documentType) {
  return `هل تريد حذف النوع «${documentType.name}» نهائيًا؟ هذا الإجراء مخصص للأنواع غير المستخدمة فقط، ولن يمكن التراجع عنه من هذه الشاشة.`;
}

function getEmptyStateMessage(filters) {
  if (filters.search || filters.status !== "all") {
    return "لا توجد أنواع وثائق تطابق الاسم العربي أو الحالة المحددة. جرّب تعديل البحث أو إعادة الضبط.";
  }

  return "لا توجد أنواع وثائق حتى الآن. أضف أول نوع ليظهر في القوائم العامة والنماذج الجديدة.";
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
          <small className="muted">سيظهر هذا الاسم مباشرة في القوائم العامة ونماذج اختيار نوع الوثيقة.</small>
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
  const [draftFilters, setDraftFilters] = useState(createDefaultFilters());
  const [appliedFilters, setAppliedFilters] = useState(() => buildAppliedFilters(createDefaultFilters()));
  const [page, setPage] = useState(1);
  const [count, setCount] = useState(0);
  const [hasNextPage, setHasNextPage] = useState(false);
  const [hasPreviousPage, setHasPreviousPage] = useState(false);

  const loadDocumentTypes = useCallback(async (targetPage, showLoadingState = false) => {
    if (showLoadingState) {
      setIsLoading(true);
    }

    try {
      const params = { page: targetPage };

      if (appliedFilters.search) {
        params.search = appliedFilters.search;
      }

      if (appliedFilters.status !== "all") {
        params.status = appliedFilters.status;
      }

      const response = await getManagedDocumentTypes(params);
      setDocumentTypes(response.results || []);
      setCount(response.count || 0);
      setHasNextPage(Boolean(response.next));
      setHasPreviousPage(Boolean(response.previous));
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
  }, [appliedFilters]);

  useEffect(() => {
    if (!user || user.role !== "admin") {
      return;
    }

    loadDocumentTypes(page, true);
  }, [loadDocumentTypes, page, user]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      const nextFilters = buildAppliedFilters(draftFilters);
      setPage(1);
      setAppliedFilters((current) => {
        if (current.search === nextFilters.search && current.status === nextFilters.status) {
          return current;
        }
        return nextFilters;
      });
    }, 250);

    return () => window.clearTimeout(timeoutId);
  }, [draftFilters]);

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
    const nextName = createForm.name.trim();

    setCreateError("");
    setPageError("");
    setSuccessMessage("");
    setIsCreateSubmitting(true);

    try {
      await createManagedDocumentType({
        name: nextName,
        is_active: createForm.is_active,
      });
      setCreateForm(createEmptyForm());
      setPage(1);
      await loadDocumentTypes(1, false);
      setSuccessMessage(getCreateSuccessMessage(createForm.is_active));
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

    const nextValues = {
      name: editForm.name.trim(),
      is_active: editForm.is_active,
    };

    if (editingType.is_active && !nextValues.is_active) {
      const confirmed = window.confirm(getDeactivateConfirmationMessage(editingType));
      if (!confirmed) {
        return;
      }
    }

    setEditError("");
    setPageError("");
    setSuccessMessage("");
    setIsEditSubmitting(true);

    try {
      await updateManagedDocumentType(editingType.id, nextValues);
      await loadDocumentTypes(page, false);
      handleCloseEdit();
      setSuccessMessage(getUpdateSuccessMessage(editingType, nextValues));
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
        ? getReactivateConfirmationMessage(documentType)
        : getDeactivateConfirmationMessage(documentType)
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
      setSuccessMessage(
        nextIsActive
          ? "تمت إعادة تفعيل نوع الوثيقة، وسيظهر مجددًا في القوائم العامة والنماذج الجديدة."
          : "تم تعطيل نوع الوثيقة. سيبقى اسمه ظاهرًا في الوثائق المرتبطة به فقط."
      );
    } catch (error) {
      setPageError(
        getApiErrorMessage(
          error,
          nextIsActive ? "تعذر إعادة تفعيل نوع الوثيقة." : "تعذر تعطيل نوع الوثيقة."
        )
      );
    } finally {
      setIsActionSubmitting(false);
    }
  }

  async function handleDelete(documentType) {
    const confirmed = window.confirm(getDeleteConfirmationMessage(documentType));
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
      setSuccessMessage("تم حذف نوع الوثيقة نهائيًا لأنه غير مستخدم في أي وثيقة.");
    } catch (error) {
      setPageError(getApiErrorMessage(error, "تعذر حذف نوع الوثيقة."));
    } finally {
      setIsActionSubmitting(false);
    }
  }

  function handleFiltersSubmit(event) {
    event.preventDefault();
    const nextFilters = buildAppliedFilters(draftFilters);
    setPage(1);
    setAppliedFilters(nextFilters);
  }

  function handleResetFilters() {
    const nextFilters = createDefaultFilters();
    setDraftFilters(nextFilters);
    setAppliedFilters(buildAppliedFilters(nextFilters));
    setPage(1);
  }

  const totalPages = Math.max(1, Math.ceil(count / DEFAULT_PAGE_SIZE));

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
        subtitle="تعديل الأسماء، تعطيل الأنواع المستخدمة بأمان، وحذف الأنواع غير المستخدمة من لوحة واحدة."
      />

      <AlertMessage type="success" message={successMessage} />
      <AlertMessage type="error" message={pageError} />

      <div className="user-management-grid">
        <div className="card">
          <div className="control-panel-card__header">
            <div>
              <h3>إضافة نوع جديد</h3>
              <p className="muted">النوع النشط يظهر مباشرة في القوائم العامة ونماذج إنشاء وتعديل الوثائق.</p>
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
              <h3>قواعد الإدارة الآمنة</h3>
              <p className="muted">القائمة العامة تعرض الأنواع النشطة فقط، بينما تبقى أسماء الأنواع غير النشطة ظاهرة داخل الوثائق القديمة المرتبطة بها.</p>
            </div>
          </div>

          <div className="control-panel-rules">
            <p>
              يمكن <strong>إعادة تسمية</strong> النوع في أي وقت ما دام الاسم العربي غير مكرر بعد التطبيع.
            </p>
            <p>
              يمكن <strong>تعطيل</strong> النوع المستخدم من دون التأثير على الوثائق القديمة، لكنه سيتوقف عن الظهور في النماذج الجديدة.
            </p>
            <p>
              يمكن <strong>حذف</strong> النوع فقط إذا كان غير مستخدم في أي وثيقة.
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
            <p className="muted">ابحث بالاسم العربي فقط، ثم طبّق الحالة المطلوبة لمعرفة ما يمكن تعديله أو تعطيله أو حذفه بأمان.</p>
          </div>
        </div>

        <form className="filters-grid document-types-toolbar" onSubmit={handleFiltersSubmit}>
          <label className="form-field full-row">
            <span>الاسم العربي</span>
            <input
              type="text"
              value={draftFilters.search}
              onChange={(event) =>
                setDraftFilters((current) => ({ ...current, search: event.target.value }))
              }
              placeholder="اكتب جزءًا من اسم النوع"
              aria-label="بحث أنواع الوثائق بالاسم العربي"
            />
          </label>

          <label className="form-field">
            <span>الحالة</span>
            <select
              value={draftFilters.status}
              onChange={(event) =>
                setDraftFilters((current) => ({ ...current, status: event.target.value }))
              }
            >
              <option value="all">الكل</option>
              <option value="active">النشطة فقط</option>
              <option value="inactive">غير النشطة فقط</option>
            </select>
          </label>

          <div className="document-types-toolbar__actions">
            <button type="submit">تطبيق</button>
            <button type="button" className="btn-secondary" onClick={handleResetFilters}>
              إعادة الضبط
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
                  <th>عدد الاستخدامات</th>
                  <th>الإجراءات</th>
                </tr>
              </thead>
              <tbody>
                {documentTypes.map((documentType) => (
                  <tr key={documentType.id}>
                    <td>
                      <div className="document-type-name-cell">
                        <strong>{documentType.name}</strong>
                      </div>
                    </td>
                    <td>
                      <span className={`state-pill ${documentType.is_active ? "state-pill--active" : "state-pill--inactive"}`}>
                        {documentType.is_active ? "نشط" : "غير نشط"}
                      </span>
                    </td>
                    <td>
                      <div className="document-type-usage-cell">
                        <span
                          className={`document-type-usage ${documentType.usage_count ? "document-type-usage--used" : "document-type-usage--unused"}`}
                        >
                          {documentType.usage_count}
                        </span>
                        <span className="muted">{formatUsageLabel(documentType.usage_count)}</span>
                      </div>
                    </td>
                    <td>
                      <div className="user-actions">
                        <button
                          type="button"
                          className="btn-secondary"
                          onClick={() => handleStartEdit(documentType)}
                          disabled={isActionSubmitting}
                        >
                          تعديل
                        </button>
                        {documentType.usage_count ? (
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
          <EmptyBlock message={getEmptyStateMessage(appliedFilters)} />
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
                <p className="muted">
                  {editingType.usage_count
                    ? `هذا النوع مرتبط حاليًا بـ ${editingType.usage_count} وثيقة، لذلك يمكن تعديل الاسم أو التعطيل بأمان مع بقاء الاسم ظاهرًا في الوثائق القديمة.`
                    : "يمكنك تعديل الاسم أو الحالة، كما يمكن حذف النوع من الجدول الرئيسي لأنه غير مستخدم."}
                </p>
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
