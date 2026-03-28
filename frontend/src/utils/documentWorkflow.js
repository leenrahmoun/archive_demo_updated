export function getDocumentWorkflowActionState(user, document, { hideSubmitAction = false } = {}) {
  const status = document?.status;
  const isDeleted = Boolean(document?.is_deleted);
  const role = user?.role;
  const isOwner = user?.id === document?.created_by;
  const isOwnerDataEntry = role === "data_entry" && isOwner;

  const canReviewRole = role === "admin" || role === "auditor";
  const canSubmitByRole = role === "admin" || isOwnerDataEntry;
  const canSubmit =
    !isDeleted &&
    canSubmitByRole &&
    (status === "draft" || status === "rejected");
  const canReview = canReviewRole && !isDeleted && status === "pending";
  const canDelete =
    !isDeleted &&
    (role === "admin" || (isOwnerDataEntry && status === "draft"));

  return {
    showSubmit: canSubmit && !hideSubmitAction,
    submitEnabled: canSubmit,
    showApprove: canReview,
    approveEnabled: canReview,
    showReject: canReview,
    rejectEnabled: canReview,
    showDelete: canDelete,
    deleteEnabled: canDelete,
  };
}

export function getDocumentDetailSubmitPlacement(user, document) {
  const status = document?.status;
  const isDeleted = Boolean(document?.is_deleted);
  const role = user?.role;
  const isOwner = user?.id === document?.created_by;
  const canUseDraftSubmitCard = !isDeleted && status === "draft" && (role === "admin" || (role === "data_entry" && isOwner));
  const canUseRejectedSubmitCard = !isDeleted && status === "rejected" && (role === "admin" || (role === "data_entry" && isOwner));

  if (canUseDraftSubmitCard) {
    return "draft-card";
  }

  if (canUseRejectedSubmitCard) {
    return "rejection-card";
  }

  return "none";
}
