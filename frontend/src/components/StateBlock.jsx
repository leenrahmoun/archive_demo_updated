export function LoadingBlock({ message = "جاري التحميل..." }) {
  return (
    <div className="state-block info">
      <p className="page-state">{message}</p>
    </div>
  );
}

export function EmptyBlock({ message = "لا توجد بيانات." }) {
  return (
    <div className="state-block">
      <p className="muted">{message}</p>
    </div>
  );
}
