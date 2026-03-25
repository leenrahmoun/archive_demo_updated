export function AlertMessage({ type = "error", message }) {
  if (!message) {
    return null;
  }
  const className = type === "success" ? "success" : type === "info" ? "page-state" : "error";
  return (
    <div className={`alert ${type}`}>
      <p className={className}>{message}</p>
    </div>
  );
}
