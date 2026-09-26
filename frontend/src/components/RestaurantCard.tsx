import { featureBadges, formatMetaLine, formatRating } from "../format";
import type { RecommendationItem } from "../types";

type RestaurantCardProps = {
  item: RecommendationItem;
};

export function RestaurantCard({ item }: RestaurantCardProps) {
  const badges = featureBadges(item);
  return (
    <article className="rounded-[12px] border border-divider bg-white p-5 shadow-[0_1px_2px_rgba(28,28,28,0.06)] transition hover:border-brand">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-brand bg-soft text-xs font-bold text-brand">
            #{item.rank}
          </span>
          <div>
            <h3 className="text-base leading-tight font-bold text-heading">{item.name}</h3>
            <p className="mt-1 text-xs text-muted">{formatMetaLine(item)}</p>
          </div>
        </div>
        <span className="inline-flex shrink-0 items-center rounded-md border border-rating-border bg-rating-bg px-2.5 py-1 text-xs font-bold text-rating">
          {formatRating(item.rating)}
        </span>
      </div>
      {badges.length > 0 ? (
        <div className="mt-3.5 flex flex-wrap items-center gap-2">
          {badges.map((badge) => (
            <span
              key={badge}
              className="rounded-full border border-divider bg-canvas px-2.5 py-0.5 text-[11px] font-medium text-body"
            >
              {badge}
            </span>
          ))}
        </div>
      ) : null}
      <p className="mt-3 border-t border-divider pt-3 text-xs leading-relaxed text-body">
        {item.explanation}
      </p>
    </article>
  );
}
