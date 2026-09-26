import type { RecommendationResponse } from "../types";
import { EmptyState } from "./EmptyState";
import { LoadingState } from "./LoadingState";
import { RestaurantCard } from "./RestaurantCard";
import { StatusBanner } from "./StatusBanner";

type ResultsPanelProps = {
  status: "idle" | "loading" | "ready" | "error";
  error: string | null;
  response: RecommendationResponse | null;
};

export function ResultsPanel({ status, error, response }: ResultsPanelProps) {
  if (status === "idle") {
    return (
      <StatusBanner tone="info" label="Ready">
        Set your preferences and select Find restaurants to see grounded recommendations.
      </StatusBanner>
    );
  }

  if (status === "error") {
    return (
      <StatusBanner tone="error" label="Error">
        {error || "Something went wrong while finding recommendations. Please try again."}
      </StatusBanner>
    );
  }

  if (status === "loading" || response == null) {
    return <LoadingState />;
  }

  const hasResults = response.results.length > 0;

  return (
    <div className="space-y-6">
      {response.engine === "fallback" ? (
        <StatusBanner tone="warning" label="Warning">
          AI ranking is temporarily unavailable. These results use ratings, popularity, and
          preference fit.
        </StatusBanner>
      ) : null}
      {response.relaxation_applied ? (
        <StatusBanner tone="info" label="Search expanded">
          {response.relaxation_applied}
        </StatusBanner>
      ) : null}
      {hasResults ? (
        <StatusBanner tone="success" label="Matches found">
          {response.summary ||
            "Here are the strongest matches for your selected preferences."}
        </StatusBanner>
      ) : null}

      {hasResults ? (
        <>
          <div className="pt-1">
            <h2 className="text-lg font-bold text-heading">
              {`Top ${response.results.length} recommendation${response.results.length === 1 ? "" : "s"}`}
            </h2>
            <p className="mt-0.5 text-xs text-muted">
              Ranked from the Bengaluru dataset, then explained for your preferences.
            </p>
          </div>
          <div className="space-y-4">
            {response.results.map((item) => (
              <RestaurantCard key={item.id} item={item} />
            ))}
          </div>
        </>
      ) : (
        <EmptyState message={response.message} />
      )}
    </div>
  );
}
