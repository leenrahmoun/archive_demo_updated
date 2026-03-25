import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { AlertMessage } from "../components/AlertMessage";
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
      <form className="card auth-card" onSubmit={onSubmit}>
        <PageHeader title="تسجيل الدخول" subtitle="أدخل بيانات الحساب للوصول إلى النظام." />
        {location.state?.reason === "unauthorized" ? <AlertMessage type="info" message="يرجى تسجيل الدخول أولا." /> : null}
        {authMessage ? <AlertMessage type="error" message={authMessage} /> : null}
        <label>
          اسم المستخدم
          <input
            value={form.username}
            onChange={(e) => setForm((prev) => ({ ...prev, username: e.target.value }))}
            required
          />
        </label>
        <label>
          كلمة المرور
          <input
            type="password"
            value={form.password}
            onChange={(e) => setForm((prev) => ({ ...prev, password: e.target.value }))}
            required
          />
        </label>
        {error ? <p className="error">{error}</p> : null}
        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "جاري الدخول..." : "دخول"}
        </button>
        {authMessage ? (
          <button type="button" className="btn-secondary" onClick={() => setAuthMessage("")}>
            إخفاء الرسالة
          </button>
        ) : null}
      </form>
    </div>
  );
}
