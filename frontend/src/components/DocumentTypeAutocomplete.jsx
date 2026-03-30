import { useMemo, useState } from "react";

function normalizeArabicSearch(value) {
  return (value || "")
    .toLowerCase()
    .normalize("NFKC")
    .replace(/[\u064b-\u065f\u0670]/g, "")
    .replace(/[أإآ]/g, "ا")
    .replace(/ى/g, "ي")
    .replace(/[ؤئ]/g, "ي")
    .replace(/ة/g, "ه")
    .replace(/\s+/g, " ")
    .trim();
}

function cleanDocumentTypeName(value) {
  return (value || "").replace(/\s+/g, " ").trim();
}

function buildResolvedOptions(options, value, selectedLabel) {
  const hasSelectedOption = options.some((option) => String(option?.id) === String(value));
  const fallbackOption =
    value && selectedLabel && !hasSelectedOption
      ? [{ id: value, name: selectedLabel, is_active: false, isLegacySelection: true }]
      : [];

  const uniqueOptions = [];
  const seenIds = new Set();
  const seenNames = new Set();

  for (const option of [...fallbackOption, ...options]) {
    const optionId = String(option?.id ?? "");
    const optionName = cleanDocumentTypeName(option?.name);
    const normalizedName = normalizeArabicSearch(optionName);

    if (!optionId || !optionName || seenIds.has(optionId)) {
      continue;
    }
    if (normalizedName && seenNames.has(normalizedName)) {
      continue;
    }

    seenIds.add(optionId);
    if (normalizedName) {
      seenNames.add(normalizedName);
    }

    uniqueOptions.push({
      ...option,
      name: optionName,
      is_active: option?.is_active !== false,
    });
  }

  return uniqueOptions;
}

export function DocumentTypeAutocomplete({
  options,
  value,
  selectedLabel = "",
  onChange,
  label = "نوع الوثيقة",
  placeholder = "ابدأ بكتابة نوع الوثيقة",
  helperText = "اكتب جزءًا من الاسم العربي لعرض الأنواع المطابقة.",
  inactiveSelectionHelperText = "النوع الحالي غير نشط، لكنه يبقى ظاهرًا هنا للحفاظ على اختيار هذه الوثيقة.",
  errorText = "",
  required = false,
}) {
  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);

  const resolvedOptions = useMemo(
    () => buildResolvedOptions(options, value, selectedLabel),
    [options, selectedLabel, value]
  );
  const selectedOption = useMemo(
    () => resolvedOptions.find((option) => String(option.id) === String(value)) || null,
    [resolvedOptions, value]
  );
  const selectedName = selectedOption?.name || (value ? cleanDocumentTypeName(selectedLabel) : "") || "";
  const hasResolvedSelection = Boolean(selectedOption || (value && selectedLabel));
  const inputValue = isOpen ? query : selectedName || query;
  const normalizedQuery = useMemo(() => normalizeArabicSearch(query), [query]);

  const filteredOptions = useMemo(() => {
    if (!normalizedQuery) {
      return resolvedOptions;
    }

    return resolvedOptions.filter((option) =>
      normalizeArabicSearch(option.name).includes(normalizedQuery)
    );
  }, [normalizedQuery, resolvedOptions]);

  const helperMessage = selectedOption?.is_active === false
    ? inactiveSelectionHelperText
    : helperText;

  function handleInputChange(event) {
    const nextQuery = event.target.value;
    setQuery(nextQuery);
    setIsOpen(true);

    if (hasResolvedSelection && nextQuery !== selectedName) {
      onChange("");
    }
  }

  function handleOptionSelect(option) {
    onChange(String(option.id));
    setQuery(option.name);
    setIsOpen(false);
  }

  return (
    <div className="form-field full-row document-type-picker">
      <span>{label}{required ? " *" : ""}</span>
      <input
        type="text"
        value={inputValue}
        placeholder={placeholder}
        aria-label={label}
        autoComplete="off"
        onFocus={() => {
          setIsOpen(true);
          setQuery(selectedName || query);
        }}
        onBlur={() => {
          window.setTimeout(() => {
            setIsOpen(false);
            setQuery(hasResolvedSelection ? selectedName : "");
          }, 120);
        }}
        onChange={handleInputChange}
      />
      {errorText ? <small className="form-field__error">{errorText}</small> : null}
      {!errorText && helperMessage ? <small className="muted">{helperMessage}</small> : null}

      {isOpen ? (
        <div className="document-type-picker__panel">
          {filteredOptions.length ? (
            <div className="document-type-picker__list" role="listbox" aria-label={`${label} suggestions`}>
              {filteredOptions.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  className={`document-type-picker__option${
                    String(option.id) === String(value) ? " document-type-picker__option--selected" : ""
                  }`}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => handleOptionSelect(option)}
                >
                  <span className="document-type-picker__option-name">{option.name}</span>
                  {option.is_active === false ? (
                    <span className="document-type-picker__option-meta">
                      غير نشط، متاح للحفاظ على الاختيار الحالي فقط
                    </span>
                  ) : null}
                </button>
              ))}
            </div>
          ) : (
            <div className="document-type-picker__empty">
              {normalizedQuery
                ? "لا توجد أنواع وثائق مطابقة للاسم المكتوب."
                : "لا توجد أنواع وثائق نشطة متاحة حاليًا."}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
