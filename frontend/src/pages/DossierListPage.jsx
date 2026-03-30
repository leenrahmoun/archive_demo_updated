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
    () => Math.max(1, Math.ceil((data.count || 0) / DEFAULT_PAGE_SIZE)),
    [data.count]
  );

  return (
    <section>
      <PageHeader title="قائمة الأضابير" subtitle="بحث وتصفية الأضابير مع عرض منسق للنتائج." />

      <FilterSection>
        <input
          placeholder="بحث: رقم الإضبارة / الاسم / الرقم الوطني"
          aria-label="بحث: رقم الإضبارة / الاسم / الرقم الوطني"
          value={filters.search}
          onChange={(event) => {
            setIsLoading(true);
            setPage(1);
            setFilters((prev) => ({ ...prev, search: event.target.value }));
          }}
        />
        <select
          value={filters.governorate}
          onChange={(event) => {
            setIsLoading(true);
            setPage(1);
            setFilters((prev) => ({ ...prev, governorate: event.target.value }));
          }}
        >
          <option value="">كل المحافظات</option>
          {governorates.map((gov) => (
            <option key={gov.id} value={gov.id}>
              {gov.name}
            </option>
          ))}
        </select>
      </FilterSection>

      <AlertMessage type="error" message={error} />
      {isLoading ? <LoadingBlock /> : null}

      {!isLoading ? (
        <div className="card">
          <table className="data-table">
            <thead>
              <tr>
                <th>رقم الإضبارة</th>
                <th>الاسم</th>
                <th>الرقم الوطني</th>
                <th>المحافظة</th>
                <th>التفاصيل</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((dossier) => (
                <tr key={dossier.id}>
                  <td>{dossier.file_number}</td>
                  <td>{dossier.full_name}</td>
                  <td>{dossier.national_id}</td>
                  <td>{dossier.governorate_name || dossier.governorate || "-"}</td>
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
