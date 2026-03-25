export function PageHeader({ title, subtitle }) {
  return (
    <header className="page-header">
      <h2>{title}</h2>
      {subtitle ? <p className="muted">{subtitle}</p> : null}
    </header>
  );
}
