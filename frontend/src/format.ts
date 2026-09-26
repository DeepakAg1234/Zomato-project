import type { Preferences, RecommendationItem } from "./types";

const BUDGET_HINT: Record<Preferences["budget"], string> = {
  low: "Low budget matches up to ₹400 for two",
  medium: "Medium budget matches ₹401–₹1,000 for two",
  high: "High budget matches above ₹1,000 for two",
};

export function budgetHint(budget: Preferences["budget"]): string {
  return BUDGET_HINT[budget];
}

export function activePreferenceCount(preferences: Preferences): number {
  let count = 1;
  if (preferences.locality) count += 1;
  if (preferences.cityZone) count += 1;
  if (preferences.cuisines.length > 0) count += 1;
  if (preferences.minRating > 0) count += 1;
  if (preferences.extra.trim()) count += 1;
  return count;
}

export function formatRating(rating: number | null): string {
  return rating == null ? "Not rated" : `${rating.toFixed(1)} ★`;
}

export function formatCost(costForTwo: number | null): string {
  if (costForTwo == null) return "Cost not listed";
  return `≈ ₹${costForTwo.toLocaleString("en-IN")} for two`;
}

export function formatCuisines(cuisines: string[]): string {
  return cuisines.length > 0 ? cuisines.join(", ") : "Cuisine not listed";
}

export function formatMetaLine(item: RecommendationItem): string {
  const parts = [formatCuisines(item.cuisines), formatCost(item.cost_for_two)];
  if (item.locality) parts.push(item.locality);
  return parts.join(" · ");
}

export function featureBadges(item: RecommendationItem): string[] {
  const badges: string[] = [];
  if (item.book_table) badges.push("Table booking");
  if (item.online_order) badges.push("Online ordering");
  return badges;
}
