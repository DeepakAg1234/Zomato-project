import { useMemo, useState } from "react";
import { CheckIcon } from "./icons";

type CuisineChipsProps = {
  cuisines: string[];
  selected: string[];
  onChange: (selected: string[]) => void;
};

export function CuisineChips({ cuisines, selected, onChange }: CuisineChipsProps) {
  const [query, setQuery] = useState("");
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return cuisines;
    return cuisines.filter((cuisine) => cuisine.toLowerCase().includes(needle));
  }, [cuisines, query]);

  function toggle(cuisine: string) {
    if (selected.includes(cuisine)) {
      onChange(selected.filter((item) => item !== cuisine));
      return;
    }
    onChange([...selected, cuisine]);
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-3">
        <label htmlFor="cuisine-filter" className="text-xs font-semibold text-heading">
          Cuisines
        </label>
        <span className="text-[10px] text-muted">
          {selected.length === 0 ? "Any cuisine" : `${selected.length} selected`}
        </span>
      </div>
      <input
        id="cuisine-filter"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Filter cuisines"
        className="mb-2 w-full rounded-lg border border-divider px-3 py-2 text-xs text-heading placeholder:text-muted focus:border-brand focus:ring-1 focus:ring-brand focus:outline-none"
      />
      <div className="flex max-h-40 flex-wrap gap-2 overflow-y-auto pr-1">
        {visible.length === 0 ? (
          <p className="text-[11px] text-muted">No cuisines match that filter.</p>
        ) : (
          visible.map((cuisine) => {
            const isSelected = selected.includes(cuisine);
            return (
              <button
                key={cuisine}
                type="button"
                aria-pressed={isSelected}
                onClick={() => toggle(cuisine)}
                className={
                  isSelected
                    ? "inline-flex items-center gap-1 rounded-full border border-brand bg-soft px-3 py-1.5 text-xs font-semibold text-brand shadow-[0_1px_2px_rgba(28,28,28,0.06)]"
                    : "inline-flex items-center rounded-full border border-divider bg-white px-3 py-1.5 text-xs font-medium text-body transition hover:border-neutral-400 hover:text-heading"
                }
              >
                {isSelected ? <CheckIcon /> : null}
                {cuisine}
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
