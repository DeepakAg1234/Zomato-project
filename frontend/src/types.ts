export type Budget = "low" | "medium" | "high";

export type MetaResponse = {
  localities: string[];
  city_zones: string[];
  cuisines: string[];
  budget_bands: string[];
};

export type RecommendationItem = {
  id: string;
  rank: number;
  name: string;
  cuisines: string[];
  rating: number | null;
  votes: number;
  cost_for_two: number | null;
  locality: string;
  online_order: boolean;
  book_table: boolean;
  explanation: string;
};

export type RecommendationResponse = {
  summary: string | null;
  relaxation_applied: string | null;
  engine: "llm" | "fallback" | "none";
  results: RecommendationItem[];
  message: string | null;
};

export type Preferences = {
  locality: string | null;
  cityZone: string | null;
  budget: Budget;
  cuisines: string[];
  minRating: number;
  maxResults: number;
  extra: string;
};

export const INITIAL_PREFERENCES: Preferences = {
  locality: null,
  cityZone: null,
  budget: "medium",
  cuisines: [],
  minRating: 4,
  maxResults: 5,
  extra: "",
};
