import { activePreferenceCount, budgetHint } from "../format";
import type { Budget, MetaResponse, Preferences } from "../types";
import { CuisineChips } from "./CuisineChips";
import { PreferenceTextArea } from "./PreferenceTextArea";
import { PrimaryButton } from "./PrimaryButton";
import { SegmentedControl } from "./SegmentedControl";
import { SelectField } from "./SelectField";
import { SliderField } from "./SliderField";

type PreferencePanelProps = {
  meta: MetaResponse;
  preferences: Preferences;
  loading: boolean;
  onChange: (preferences: Preferences) => void;
  onSubmit: () => void;
};

export function PreferencePanel({
  meta,
  preferences,
  loading,
  onChange,
  onSubmit,
}: PreferencePanelProps) {
  const active = activePreferenceCount(preferences);

  return (
    <aside className="w-full space-y-6 rounded-[12px] border border-divider bg-white p-6 shadow-[0_1px_2px_rgba(28,28,28,0.06)] lg:sticky lg:top-8">
      <div className="flex items-center justify-between border-b border-divider pb-3">
        <div>
          <h2 className="text-sm font-bold tracking-wide text-heading uppercase">
            Your preferences
          </h2>
          <p className="text-[11px] text-muted">Tailor criteria for ranking</p>
        </div>
        <span className="rounded bg-soft px-2 py-0.5 text-[10px] font-semibold text-brand">
          {active} active
        </span>
      </div>
      <form
        className="space-y-5"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <SelectField
          id="locality"
          label="Locality"
          value={preferences.locality ?? ""}
          emptyLabel="Any locality"
          options={meta.localities}
          onChange={(value) =>
            onChange({ ...preferences, locality: value || null })
          }
        />
        <SelectField
          id="city-zone"
          label="City zone"
          value={preferences.cityZone ?? ""}
          emptyLabel="Any city zone"
          options={meta.city_zones}
          onChange={(value) =>
            onChange({ ...preferences, cityZone: value || null })
          }
        />
        <div>
          <p className="mb-2 text-xs font-semibold text-heading">Budget</p>
          <SegmentedControl
            value={preferences.budget}
            onChange={(budget: Budget) => onChange({ ...preferences, budget })}
          />
          <p className="mt-1 text-[10px] text-muted">{budgetHint(preferences.budget)}</p>
        </div>
        <CuisineChips
          cuisines={meta.cuisines}
          selected={preferences.cuisines}
          onChange={(cuisines) => onChange({ ...preferences, cuisines })}
        />
        <div className="space-y-4 pt-1">
          <SliderField
            id="min-rating"
            label="Minimum rating"
            min={0}
            max={5}
            step={0.1}
            value={preferences.minRating}
            display={`${preferences.minRating.toFixed(1)} ★`}
            ticks={["0.0", "2.5", "5.0"]}
            onChange={(minRating) =>
              onChange({
                ...preferences,
                minRating: Math.round(minRating * 10) / 10,
              })
            }
          />
          <SliderField
            id="max-results"
            label="Number of recommendations"
            min={3}
            max={5}
            step={1}
            value={preferences.maxResults}
            display={String(preferences.maxResults)}
            ticks={["3", "4", "5"]}
            onChange={(maxResults) => onChange({ ...preferences, maxResults })}
          />
        </div>
        <PreferenceTextArea
          value={preferences.extra}
          onChange={(extra) => onChange({ ...preferences, extra })}
        />
        <div className="pt-2">
          <PrimaryButton loading={loading} />
        </div>
      </form>
    </aside>
  );
}
