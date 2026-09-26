type AppHeaderProps = {
  onReset: () => void;
  resetDisabled?: boolean;
};

export function AppHeader({ onReset, resetDisabled = false }: AppHeaderProps) {
  return (
    <header className="rounded-xl border border-divider bg-white p-4 shadow-[0_1px_2px_rgba(28,28,28,0.06)] sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand text-xl font-bold text-white shadow-sm">
            BR
          </div>
          <div>
            <div className="flex items-center gap-2.5">
              <h1 className="text-lg font-bold leading-tight tracking-tight text-heading">
                Bengaluru Restaurant Finder
              </h1>
              <span className="rounded-full border border-brand bg-soft px-2 py-0.5 text-[11px] font-semibold text-brand">
                AI Match
              </span>
            </div>
            <p className="mt-0.5 text-xs text-muted">
              Searching the Bengaluru restaurant dataset
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <div className="hidden items-center gap-2 rounded-lg border border-divider bg-canvas px-3.5 py-1.5 text-muted md:flex">
            <span className="h-2 w-2 rounded-full bg-rating" />
            Dataset-backed search
          </div>
          <button
            type="button"
            onClick={onReset}
            disabled={resetDisabled}
            className="font-medium text-muted transition hover:text-brand disabled:cursor-not-allowed disabled:opacity-50"
          >
            Reset filters
          </button>
        </div>
      </div>
    </header>
  );
}
