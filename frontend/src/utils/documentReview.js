export function getApprovalOriginLabel(document) {
  if (!document || document.status !== "approved") {
    return "";
  }

  if (document.reviewed_by_role === "admin") {
    return "تم الاعتماد من المدير";
  }

  if (document.reviewed_by_role === "auditor") {
    return "تم الاعتماد من المدقق";
  }

  if (document.reviewed_by_name) {
    return `تم الاعتماد بواسطة ${document.reviewed_by_name}`;
  }

  return "تم الاعتماد";
}

export function getApprovalOriginTone(document) {
  if (!document || document.status !== "approved") {
    return "";
  }

  if (document.reviewed_by_role === "admin") {
    return "admin";
  }

  if (document.reviewed_by_role === "auditor") {
    return "auditor";
  }

  return "neutral";
}
