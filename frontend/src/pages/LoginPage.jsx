import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { AlertMessage } from "../components/AlertMessage";
import { BrandLockup } from "../components/BrandLockup";
import { PageHeader } from "../components/PageHeader";

export function LoginPage() {
  const { isAuthenticated, login, authMessage, setAuthMessage } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const from = location.state?.from?.pathname || "/dossiers";

  if (isAuthenticated) {
    return <Navigate to="/dossiers" replace />;
  }

  async function onSubmit(event) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      await login(form.username, form.password);
      navigate(from, { replace: true });
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(detail || "تعذر تسجيل الدخول. تحقق من البيانات.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-shell">
        <section className="auth-brand-panel">
          <BrandLockup
            className="auth-brand-panel__lockup"
            title="وزارة التنمية الإدارية"
            subtitle="النظام الداخلي للأرشفة وإدارة الوثائق"
            note="واجهة مؤسسية رسمية لمتابعة الأضابير والوثائق وسير المراجعة."
          />

          <div className="auth-brand-panel__body">
            <h2>بيئة عمل رسمية وواضحة لفريق الأرشفة والمراجعة</h2>
            <p>
              صُممت الواجهة لتكون هادئة، سهلة القراءة، ومتوافقة مع الاستخدام اليومي داخل
              المؤسسة مع تركيز واضح على العربية واتساق الصلاحيات.
            </p>
          </div>

          <div className="auth-brand-panel__highlights">
            <div className="auth-brand-panel__highlight">
              <strong>وصول آمن</strong>
              <span>الصلاحيات تحترم الدور والنطاق في كل خطوة.</span>
            </div>
            <div className="auth-brand-panel__highlight">
              <strong>متابعة رسمية</strong>
              <span>تنقّل واضح بين الأضابير والوثائق والمراجعات.</span>
            </div>
            <div className="auth-brand-panel__highlight">
              <strong>واجهة عربية</strong>
              <span>قراءة أسهل ومساحات أهدأ تناسب العمل اليومي.</span>
            </div>
          </div>
        </section>

        <form className="card auth-card" onSubmit={onSubmit}>
          <div className="auth-card__brand">
            <BrandLockup compact title="تسجيل الدخول" subtitle="الدخول إلى النظام المؤسسي" />
          </div>

          <PageHeader
            title="الدخول إلى النظام"
            subtitle="أدخل بيانات الحساب للوصول إلى منصة الأرشفة الداخلية."
          />

          {location.state?.reason === "unauthorized" ? (
            <AlertMessage type="info" message="يرجى تسجيل الدخول أولًا." />
          ) : null}
          {authMessage ? <AlertMessage type="error" message={authMessage} /> : null}

          <label className="auth-card__field">
            <span>اسم المستخدم</span>
            <input
              value={form.username}
              onChange={(event) => setForm((prev) => ({ ...prev, username: event.target.value }))}
              required
            />
          </label>

          <label className="auth-card__field">
            <span>كلمة المرور</span>
            <input
              type="password"
              value={form.password}
              onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
              required
            />
          </label>

          {error ? <p className="error">{error}</p> : null}

          <div className="auth-card__actions">
            <button type="submit" className="btn-primary auth-card__submit" disabled={isSubmitting}>
              {isSubmitting ? "جارٍ تسجيل الدخول..." : "دخول"}
            </button>

            {authMessage ? (
              <button type="button" className="btn-secondary" onClick={() => setAuthMessage("")}>
                إخفاء الرسالة
              </button>
            ) : null}
          </div>
        </form>
      </div>
    </div>
  );
}
