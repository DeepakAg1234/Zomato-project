import { SearchIcon } from "./icons";

type EmptyStateProps = {
  message?: string | null;
};

export function EmptyState({ message }: EmptyStateProps) {
  return (
    <div className="flex min-h-[200px] flex-col items-center justify-center rounded-[12px] border border-divider bg-white p-7 text-center shadow-[0_1px_2px_rgba(28,28,28,0.06)]">
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-soft text-brand">
        <SearchIcon />
      </div>
      <h2 className="text-sm font-bold text-heading">No matching restaurants found</h2>
      <p className="mt-1 max-w-xs text-xs leading-relaxed text-muted">
        {message || "Try relaxing one or more filters."}
      </p>
      <p className="mt-2 max-w-xs text-[11px] leading-relaxed text-muted">
        Try a lower minimum rating, another budget, fewer cuisines, or a city-wide search.
      </p>
    </div>
  );
}
