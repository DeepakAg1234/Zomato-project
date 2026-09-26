import { ChevronDown } from "./icons";

type SelectFieldProps = {
  id: string;
  label: string;
  value: string;
  emptyLabel: string;
  options: string[];
  onChange: (value: string) => void;
};

export function SelectField({
  id,
  label,
  value,
  emptyLabel,
  options,
  onChange,
}: SelectFieldProps) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-xs font-semibold text-heading">
        {label}
      </label>
      <div className="relative">
        <select
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="w-full cursor-pointer appearance-none rounded-lg border border-divider bg-white px-3.5 py-2.5 text-xs font-medium text-heading transition focus:border-brand focus:ring-1 focus:ring-brand focus:outline-none"
        >
          <option value="">{emptyLabel}</option>
          {options.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-3 text-muted">
          <ChevronDown />
        </div>
      </div>
    </div>
  );
}
