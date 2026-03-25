import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getAuditLogById } from "../api/auditLogsApi";
import { AlertMessage } from "../components/AlertMessage";
import { PageHeader } from "../components/PageHeader";
import { EmptyBlock, LoadingBlock } from "../components/StateBlock";
import { formatDate, stringifyJson } from "../utils/format";

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

  return (
    <section>
      <PageHeader title="تفاصيل سجل التدقيق" subtitle="عرض القيم السابقة والجديدة بصيغة مقروءة." />
      <div className="card details-grid">
        <p>
          <strong>ID:</strong> {log.id}
        </p>
        <p>
          <strong>الإجراء:</strong> {log.action}
        </p>
        <p>
          <strong>الكيان:</strong> {log.entity_type}
        </p>
        <p>
          <strong>معرف الكيان:</strong> {log.entity_id}
        </p>
        <p>
          <strong>الفاعل:</strong> {log.actor?.username || "-"}
        </p>
        <p>
          <strong>دور الفاعل:</strong> {log.actor?.role || "-"}
        </p>
        <p>
          <strong>IP:</strong> {log.ip_address || "-"}
        </p>
        <p>
          <strong>التاريخ:</strong> {formatDate(log.created_at)}
        </p>
      </div>

      <div className="card">
        <h3>القيم السابقة</h3>
        <pre className="json-box">{stringifyJson(log.old_values)}</pre>
      </div>

      <div className="card">
        <h3>القيم الجديدة</h3>
        <pre className="json-box">{stringifyJson(log.new_values)}</pre>
      </div>
    </section>
  );
}
