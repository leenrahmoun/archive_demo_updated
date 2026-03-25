import { Link } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";

export function ForbiddenPage() {
  return (
    <section className="card">
      <PageHeader title="غير مصرح" subtitle="ليس لديك صلاحية للوصول إلى هذه الصفحة." />
      <Link to="/dossiers">العودة إلى الصفحة الرئيسية</Link>
    </section>
  );
}
