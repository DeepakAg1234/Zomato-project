const MAX_CHARS = 300;

type PreferenceTextAreaProps = {
  value: string;
  onChange: (value: string) => void;
};

export function PreferenceTextArea({ value, onChange }: PreferenceTextAreaProps) {
  return (
    <div>
      <label htmlFor="extra-preferences" className="mb-1.5 block text-xs font-semibold text-heading">
        Anything else?
      </label>
      <textarea
        id="extra-preferences"
        rows={2}
        maxLength={MAX_CHARS}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="e.g. family-friendly, quick service, good for a date"
        className="w-full resize-none rounded-lg border border-divider p-3 text-xs text-heading placeholder:text-neutral-400 focus:border-brand focus:ring-1 focus:ring-brand focus:outline-none"
      />
      <div className="mt-1 flex items-center justify-between text-[10px] text-muted">
        <span>Used only to rank and explain the shortlist</span>
        <span>
          {value.length}/{MAX_CHARS}
        </span>
      </div>
    </div>
  );
}
