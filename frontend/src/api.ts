import type { MetaResponse, Preferences, RecommendationResponse } from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/+$/, "");

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail.trim()) {
      return body.detail;
    }
    if (Array.isArray(body.detail)) {
      const messages = body.detail
        .map((item) =>
          item && typeof item === "object" && "msg" in item
            ? String(item.msg)
            : "",
        )
        .filter(Boolean);
      if (messages.length > 0) return messages.join(" ");
    }
  } catch {
    /* Response body was not JSON. */
  }
  if (response.status === 503) {
    return "The restaurant catalogue is not ready.";
  }
  return "Something went wrong while finding recommendations. Please try again.";
}

export async function fetchMeta(): Promise<MetaResponse> {
  const response = await fetch(`${API_BASE}/meta`);
  if (!response.ok) throw new Error(await readError(response));
  return response.json() as Promise<MetaResponse>;
}

export async function fetchRecommendations(
  preferences: Preferences,
): Promise<RecommendationResponse> {
  const response = await fetch(`${API_BASE}/recommendations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      locality: preferences.locality,
      city_zone: preferences.cityZone,
      any_area: preferences.locality == null && preferences.cityZone == null,
      budget: preferences.budget,
      cuisines: preferences.cuisines,
      min_rating: preferences.minRating,
      extra_preferences: preferences.extra.trim(),
      max_results: preferences.maxResults,
    }),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json() as Promise<RecommendationResponse>;
}
