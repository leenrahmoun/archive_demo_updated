import { Link } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";

export function NotFoundPage() {
  return (
    <section className="card">
      <PageHeader title="الصفحة غير موجودة" subtitle="المسار المطلوب غير متاح." />
      <Link to="/dossiers">العودة إلى الصفحة الرئيسية</Link>
    </section>
  );
}
