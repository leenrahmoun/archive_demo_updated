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

export function DocumentTypeAutocomplete({
  options,
  value,
  selectedLabel = "",
  onChange,
  label = "نوع الوثيقة",
  placeholder = "ابدأ بكتابة نوع الوثيقة",
  helperText = "اكتب جزءًا من الاسم العربي لعرض الأنواع المطابقة.",
  required = false,
}) {
  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);

  const selectedOption = useMemo(
    () => options.find((option) => String(option.id) === String(value)) || null,
    [options, value]
  );
  const selectedName = selectedOption?.name || (value ? selectedLabel : "") || "";
  const hasResolvedSelection = Boolean(selectedOption || (value && selectedLabel));
  const inputValue = isOpen ? query : selectedName || query;

  const normalizedQuery = useMemo(() => normalizeArabicSearch(query), [query]);

  const filteredOptions = useMemo(() => {
    const seenIds = new Set();
    const matches = [];

    for (const option of options) {
      const optionId = String(option.id);
      if (seenIds.has(optionId)) {
        continue;
      }
      seenIds.add(optionId);

      if (!normalizedQuery || normalizeArabicSearch(option.name).includes(normalizedQuery)) {
        matches.push(option);
      }
    }

    return matches;
  }, [options, normalizedQuery]);

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
      <small className="muted">{selectedOption?.group_name || helperText}</small>

      {isOpen && normalizedQuery ? (
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
                  <span className="document-type-picker__option-meta">{option.group_name}</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="document-type-picker__empty">لا توجد أنواع وثائق مطابقة.</div>
          )}
        </div>
      ) : null}
    </div>
  );
}
