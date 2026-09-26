import type { Budget } from "../types";

const OPTIONS: { value: Budget; label: string }[] = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
];

type SegmentedControlProps = {
  value: Budget;
  onChange: (value: Budget) => void;
};

export function SegmentedControl({ value, onChange }: SegmentedControlProps) {
  return (
    <div
      className="grid grid-cols-3 gap-1.5 rounded-xl border border-divider bg-canvas p-1"
      role="radiogroup"
      aria-label="Budget"
    >
      {OPTIONS.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(option.value)}
            className={
              selected
                ? "rounded-lg border border-brand bg-soft py-2 text-center text-xs font-semibold text-brand shadow-[0_1px_2px_rgba(28,28,28,0.06)]"
                : "rounded-lg py-2 text-center text-xs font-medium text-muted transition hover:text-heading"
            }
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
