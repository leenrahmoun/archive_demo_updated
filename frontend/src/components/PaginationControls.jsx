export function PaginationControls({ page, totalPages, hasPrevious, hasNext, onPrevious, onNext }) {
  return (
    <div className="pagination">
      <button type="button" className="btn-secondary" disabled={!hasPrevious} onClick={onPrevious}>
        السابق
      </button>
      <span>
        الصفحة {page} من {totalPages}
      </span>
      <button type="button" className="btn-secondary" disabled={!hasNext} onClick={onNext}>
        التالي
      </button>
    </div>
  );
}
