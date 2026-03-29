import ministryLogo from "../assets/logo/ministry-logo.svg";

export function BrandLockup({
  className = "",
  title = "وزارة التطوير الإداري",
  subtitle = "نظام الأرشفة وإدارة الوثائق",
  note = "",
  compact = false,
  inverse = false,
}) {
  return (
    <div
      className={`brand-lockup${compact ? " brand-lockup--compact" : ""}${inverse ? " brand-lockup--inverse" : ""} ${className}`.trim()}
    >
      <div className="brand-lockup__logo-shell">
        <img src={ministryLogo} alt="شعار وزارة التطوير الإداري" className="brand-lockup__logo" />
      </div>
      <div className="brand-lockup__copy">
        <strong>{title}</strong>
        {subtitle ? <span>{subtitle}</span> : null}
        {note ? <small>{note}</small> : null}
      </div>
    </div>
  );
}
