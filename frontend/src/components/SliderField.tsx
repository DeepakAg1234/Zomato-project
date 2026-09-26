type SliderFieldProps = {
  id: string;
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  display: string;
  ticks: string[];
  onChange: (value: number) => void;
};

export function SliderField({
  id,
  label,
  min,
  max,
  step,
  value,
  display,
  ticks,
  onChange,
}: SliderFieldProps) {
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <label htmlFor={id} className="text-xs font-semibold text-heading">
          {label}
        </label>
        <span className="rounded bg-soft px-2 py-0.5 text-xs font-bold text-brand">{display}</span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="slider-red"
      />
      <div className="mt-1 flex justify-between text-[10px] font-medium text-muted">
        {ticks.map((tick) => (
          <span key={tick}>{tick}</span>
        ))}
      </div>
    </div>
  );
}
