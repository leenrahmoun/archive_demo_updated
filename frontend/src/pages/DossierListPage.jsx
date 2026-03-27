import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getDossiers } from "../api/dossiersApi";
import { getGovernorates } from "../api/lookupsApi";
import { AlertMessage } from "../components/AlertMessage";
import { FilterSection } from "../components/FilterSection";
import { PageHeader } from "../components/PageHeader";
import { PaginationControls } from "../components/PaginationControls";
import { EmptyBlock, LoadingBlock } from "../components/StateBlock";

const DEFAULT_PAGE_SIZE = 20;

export function DossierListPage() {
  const [governorates, setGovernorates] = useState([]);
  const [filters, setFilters] = useState({
    search: "",
    governorate: "",
    is_deleted: "",
    page_size: DEFAULT_PAGE_SIZE,
  });
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ count: 0, results: [], next: null, previous: null });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getGovernorates().then(setGovernorates).catch(() => setGovernorates([]));
  }, []);

  useEffect(() => {
    const params = { page, ...filters };
    Object.keys(params).forEach((key) => {
      if (params[key] === "") {
        delete params[key];
      }
    });

    getDossiers(params)
      .then((result) => {
        setData(result);
        setError("");
      })
      .catch(() => setError("تعذر تحميل قائمة الأضابير."))
      .finally(() => setIsLoading(false));
  }, [page, filters]);

  const totalPages = useMemo(
    () => Math.max(1, Math.ceil((data.count || 0) / Number(filters.page_size || DEFAULT_PAGE_SIZE))),
    [data.count, filters.page_size]
  );

  return (
    <section>
      <PageHeader title="قائمة الأضابير" subtitle="بحث وتصفية الأضابير مع عرض منسق للنتائج." />

      <FilterSection>
        <input
          placeholder="بحث: رقم الملف / الاسم / الرقم الوطني"
          value={filters.search}
          onChange={(e) => {
            setIsLoading(true);
            setPage(1);
            setFilters((prev) => ({ ...prev, search: e.target.value }));
          }}
        />
        <select
          value={filters.governorate}
          onChange={(e) => {
            setIsLoading(true);
            setPage(1);
            setFilters((prev) => ({ ...prev, governorate: e.target.value }));
          }}
        >
          <option value="">كل المحافظات</option>
          {governorates.map((gov) => (
            <option key={gov.id} value={gov.id}>
              {gov.name}
            </option>
          ))}
        </select>
        <select
          value={filters.is_deleted}
          onChange={(e) => {
            setIsLoading(true);
            setPage(1);
            setFilters((prev) => ({ ...prev, is_deleted: e.target.value }));
          }}
        >
          <option value="">الكل</option>
          <option value="false">غير مؤرشفة</option>
          <option value="true">مؤرشفة</option>
        </select>
        <select
          value={filters.page_size}
          onChange={(e) => {
            setIsLoading(true);
            setPage(1);
            setFilters((prev) => ({ ...prev, page_size: Number(e.target.value) }));
          }}
        >
          <option value={10}>10</option>
          <option value={20}>20</option>
          <option value={50}>50</option>
        </select>
      </FilterSection>

      <AlertMessage type="error" message={error} />
      {isLoading ? <LoadingBlock /> : null}

      {!isLoading ? (
        <div className="card">
          <table className="data-table">
            <thead>
              <tr>
                <th>رقم الملف</th>
                <th>الاسم</th>
                <th>الرقم الوطني</th>
                <th>محافظة</th>
                <th>التفاصيل</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((dossier) => (
                <tr key={dossier.id}>
                  <td>{dossier.file_number}</td>
                  <td>{dossier.full_name}</td>
                  <td>{dossier.national_id}</td>
                  <td>{dossier.governorate_name || dossier.governorate || "—"}</td>
                  <td>
                    <Link to={`/dossiers/${dossier.id}`}>عرض</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!data.results.length ? <EmptyBlock message="لا توجد نتائج." /> : null}
        </div>
      ) : null}

      <PaginationControls
        page={page}
        totalPages={totalPages}
        hasPrevious={Boolean(data.previous)}
        hasNext={Boolean(data.next)}
        onPrevious={() => {
          setIsLoading(true);
          setPage((prev) => Math.max(1, prev - 1));
        }}
        onNext={() => {
          setIsLoading(true);
          setPage((prev) => prev + 1);
        }}
      />
    </section>
  );
}
