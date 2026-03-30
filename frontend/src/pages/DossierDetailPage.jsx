import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { getDossierById } from "../api/dossiersApi";
import { AlertMessage } from "../components/AlertMessage";
import { EmptyBlock, LoadingBlock } from "../components/StateBlock";
import { PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { useAuth } from "../auth/useAuth";

const CREATE_ROLES = new Set(["admin", "data_entry"]);

export function DossierDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const canCreate = CREATE_ROLES.has(user?.role);
  const [dossier, setDossier] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getDossierById(id)
      .then((result) => {
        setDossier(result);
        setError("");
      })
      .catch(() => {
        setDossier(null);
        setError("تعذر تحميل تفاصيل الإضبارة.");
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [id]);

  if (isLoading) {
    return <LoadingBlock />;
  }

  if (error) {
    return <AlertMessage type="error" message={error} />;
  }

  if (!dossier) {
    return <EmptyBlock message="الإضبارة غير موجودة." />;
  }

  return (
    <section>
      <PageHeader title="تفاصيل الإضبارة" subtitle="عرض معلومات الإضبارة والوثائق المرتبطة بها." />
      <div className="card details-grid">
        <p>
          <strong>رقم الملف:</strong> {dossier.file_number}
        </p>
        <p>
          <strong>الاسم:</strong> {dossier.full_name}
        </p>
        <p>
          <strong>الجنسية:</strong> {dossier.nationality_display || "سورية"}
        </p>
        <p>
          <strong>الرقم الوطني:</strong> {dossier.national_id}
        </p>
        <p>
          <strong>الرقم الذاتي:</strong> {dossier.personal_id}
        </p>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3>الوثائق المرتبطة</h3>
        {canCreate ? (
          <Link to={`/dossiers/${id}/documents/new`} className="button">إضافة وثيقة</Link>
        ) : null}
      </div>
      <div className="card">
        <table className="data-table">
          <thead>
            <tr>
              <th>رقم الوثيقة</th>
              <th>اسم الوثيقة</th>
              <th>الحالة</th>
              <th>المسار</th>
            </tr>
          </thead>
          <tbody>
            {(dossier.documents || []).map((doc) => (
              <tr key={doc.id}>
                <td>{doc.doc_number}</td>
                <td>{doc.doc_name}</td>
                <td>
                  <StatusBadge status={doc.status} label={doc.status_display_label} />
                </td>
                <td className="path-text">{doc.doc_type_name || doc.doc_type}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!dossier.documents?.length ? <EmptyBlock message="لا توجد وثائق ضمن هذه الإضبارة." /> : null}
      </div>
    </section>
  );
}
