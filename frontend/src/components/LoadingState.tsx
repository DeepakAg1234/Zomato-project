function SkeletonCard({ faded = false }: { faded?: boolean }) {
  return (
    <div
      className={`space-y-3 rounded-[12px] border border-divider bg-white p-4 shadow-[0_1px_2px_rgba(28,28,28,0.06)] ${faded ? "opacity-70" : ""}`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="skeleton-box h-6 w-6 rounded" />
          <div className="skeleton-box h-4 w-32 rounded" />
        </div>
        <div className="skeleton-box h-5 w-12 rounded" />
      </div>
      <div className="skeleton-box h-3 w-48 rounded" />
      {faded ? null : (
        <div className="flex gap-2 pt-1">
          <div className="skeleton-box h-4 w-20 rounded-full" />
          <div className="skeleton-box h-4 w-24 rounded-full" />
        </div>
      )}
    </div>
  );
}

export function LoadingState() {
  return (
    <div className="space-y-3" aria-busy="true" aria-live="polite">
      <SkeletonCard />
      <SkeletonCard faded />
      <SkeletonCard faded />
    </div>
  );
}
