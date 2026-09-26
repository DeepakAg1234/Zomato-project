import { useEffect, useState } from "react";
import { fetchMeta, fetchRecommendations } from "./api";
import { AppHeader } from "./components/AppHeader";
import { PreferencePanel } from "./components/PreferencePanel";
import { ResultsPanel } from "./components/ResultsPanel";
import { StatusBanner } from "./components/StatusBanner";
import {
  INITIAL_PREFERENCES,
  type MetaResponse,
  type Preferences,
  type RecommendationResponse,
} from "./types";

type SearchStatus = "idle" | "loading" | "ready" | "error";

export function App() {
  const [meta, setMeta] = useState<MetaResponse | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [preferences, setPreferences] = useState<Preferences>(INITIAL_PREFERENCES);
  const [status, setStatus] = useState<SearchStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<RecommendationResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchMeta()
      .then((next) => {
        if (!cancelled) setMeta(next);
      })
      .catch((exc: unknown) => {
        if (!cancelled) {
          setMetaError(
            exc instanceof Error ? exc.message : "The restaurant catalogue could not be loaded.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function search() {
    setStatus("loading");
    setError(null);
    try {
      const next = await fetchRecommendations(preferences);
      setResponse(next);
      setStatus("ready");
    } catch (exc: unknown) {
      setResponse(null);
      setError(
        exc instanceof Error
          ? exc.message
          : "Something went wrong while finding recommendations. Please try again.",
      );
      setStatus("error");
    }
  }

  function reset() {
    setPreferences(INITIAL_PREFERENCES);
    setResponse(null);
    setError(null);
    setStatus("idle");
  }

  return (
    <div className="mx-auto min-h-screen max-w-[1440px] space-y-8 px-4 py-6 sm:px-8 sm:py-8">
      <AppHeader onReset={reset} resetDisabled={status === "loading" || meta == null} />
      {metaError ? (
        <StatusBanner tone="error" label="Error">
          {metaError}
        </StatusBanner>
      ) : null}
      {meta == null && metaError == null ? (
        <StatusBanner tone="info" label="Loading">
          Loading the restaurant catalogue…
        </StatusBanner>
      ) : null}
      {meta ? (
        <div className="grid grid-cols-1 items-start gap-8 lg:grid-cols-[380px_minmax(0,1fr)]">
          <PreferencePanel
            meta={meta}
            preferences={preferences}
            loading={status === "loading"}
            onChange={setPreferences}
            onSubmit={() => {
              void search();
            }}
          />
          <main>
            <ResultsPanel status={status} error={error} response={response} />
          </main>
        </div>
      ) : null}
    </div>
  );
}
