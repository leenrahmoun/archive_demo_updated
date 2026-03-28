import { useMemo, useState } from "react";
import { approveDocument, rejectDocument, softDeleteDocument, submitDocument } from "../api/documentsApi";
import { useAuth } from "../auth/useAuth";
import { flattenErrors } from "../utils/errors";
import { AlertMessage } from "./AlertMessage";

function getActionState(role, document, { hideSubmitAction = false } = {}) {
  const status = document?.status;
  const isDeleted = Boolean(document?.is_deleted);

  const canSubmitRole = role === "admin" || role === "data_entry";
  const canReviewRole = role === "admin" || role === "auditor";
  const canDeleteRole = role === "admin" || role === "data_entry";

  return {
    showSubmit: canSubmitRole && !hideSubmitAction,
    submitEnabled: canSubmitRole && !isDeleted && (status === "draft" || status === "rejected"),
    showApprove: canReviewRole,
    approveEnabled: canReviewRole && !isDeleted && status === "pending",
    showReject: canReviewRole,
    rejectEnabled: canReviewRole && !isDeleted && status === "pending",
    showDelete: canDeleteRole,
    deleteEnabled: !isDeleted && (role === "admin" || (role === "data_entry" && status === "draft")),
  };
}

export function DocumentWorkflowActions({ document, onDocumentChanged, hideSubmitAction = false }) {
  const { user } = useAuth();
  const [feedback, setFeedback] = useState({ success: "", error: "" });
  const [isWorking, setIsWorking] = useState(false);
  const [isRejectOpen, setIsRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  const actionState = useMemo(
    () => getActionState(user?.role, document, { hideSubmitAction }),
    [hideSubmitAction, user?.role, document]
  );
  const hasAnyActions = actionState.showSubmit || actionState.showApprove || actionState.showReject || actionState.showDelete;
  const status = document?.status;
  const isDeleted = Boolean(document?.is_deleted);

  const hints = [];
  if (isDeleted) {
    hints.push("الوثيقة محذوفة منطقيا ولا تقبل إجراءات إضافية.");
  } else if (status === "pending") {
    hints.push("الوثائق قيد المراجعة لا تعدل أو ترسل مرة أخرى قبل قرار المراجع.");
  } else if (status === "approved") {
    hints.push("الوثيقة المعتمدة لا تقبل إرسال أو رفض.");
  } else if (status === "rejected") {
    hints.push("الوثيقة مرفوضة. يمكنك تعديلها ثم إعادة إرسالها للمراجعة.");
  }

  async function runAction(actionFn, successMessage) {
    setFeedback({ success: "", error: "" });
    setIsWorking(true);
    try {
      const updated = await actionFn();
      setFeedback({ success: successMessage, error: "" });
      onDocumentChanged?.(updated);
      setIsRejectOpen(false);
      setRejectReason("");
    } catch (err) {
      const messages = flattenErrors(err?.response?.data);
      setFeedback({ success: "", error: messages[0] || "فشل تنفيذ العملية." });
    } finally {
      setIsWorking(false);
    }
  }

  function onSoftDelete() {
    const confirmed = window.confirm("هل أنت متأكد من حذف الوثيقة منطقيا؟");
    if (!confirmed) {
      return;
    }
    runAction(() => softDeleteDocument(document.id), "تم حذف الوثيقة منطقيا.");
  }

  if (!hasAnyActions) {
    return (
      <div className="card">
        <h3>إجراءات سير العمل</h3>
        <p className="muted">لا توجد إجراءات متاحة لهذا الدور.</p>
      </div>
    );
  }

  return (
    <div className="card">
      <h3>إجراءات سير العمل</h3>

      <div className="actions-row">
        {actionState.showSubmit ? (
          <button
            type="button"
            className="btn-primary"
            disabled={!actionState.submitEnabled || isWorking}
            onClick={() => runAction(() => submitDocument(document.id), "تم إرسال الوثيقة للمراجعة.")}
          >
            {status === "rejected" ? "إعادة إرسال" : "إرسال"}
          </button>
        ) : null}

        {actionState.showApprove ? (
          <button
            type="button"
            className="btn-primary"
            disabled={!actionState.approveEnabled || isWorking}
            onClick={() => runAction(() => approveDocument(document.id), "تم اعتماد الوثيقة.")}
          >
            اعتماد
          </button>
        ) : null}

        {actionState.showReject ? (
          <button
            type="button"
            className="btn-warning"
            disabled={!actionState.rejectEnabled || isWorking}
            onClick={() => setIsRejectOpen((prev) => !prev)}
          >
            رفض
          </button>
        ) : null}

        {actionState.showDelete ? (
          <button type="button" className="btn-danger" disabled={!actionState.deleteEnabled || isWorking} onClick={onSoftDelete}>
            حذف منطقي
          </button>
        ) : null}
      </div>
      {hints.length ? <AlertMessage type="info" message={hints[0]} /> : null}

      {isRejectOpen ? (
        <div className="reject-box">
          <label className="full-row">
            سبب الرفض
            <textarea value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} rows={3} />
          </label>
          <button
            type="button"
            className="btn-warning"
            disabled={isWorking || !rejectReason.trim()}
            onClick={() => runAction(() => rejectDocument(document.id, rejectReason.trim()), "تم رفض الوثيقة.")}
          >
            تأكيد الرفض
          </button>
        </div>
      ) : null}

      <AlertMessage type="success" message={feedback.success} />
      <AlertMessage type="error" message={feedback.error} />
    </div>
  );
}
