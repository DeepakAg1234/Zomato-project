import { ArrowIcon, Spinner } from "./icons";

type PrimaryButtonProps = {
  loading?: boolean;
  disabled?: boolean;
};

export function PrimaryButton({ loading = false, disabled = false }: PrimaryButtonProps) {
  const isDisabled = disabled || loading;
  return (
    <button
      type="submit"
      disabled={isDisabled}
      className={
        loading
          ? "flex w-full cursor-not-allowed items-center justify-center gap-2 rounded-xl bg-brand-disabled px-4 py-3 text-center text-xs font-semibold text-white"
          : "flex w-full items-center justify-center gap-2 rounded-xl bg-brand px-4 py-3 text-center text-xs font-semibold text-white shadow-[0_1px_2px_rgba(28,28,28,0.06)] transition hover:bg-brand-pressed disabled:cursor-not-allowed disabled:opacity-60"
      }
    >
      {loading ? <Spinner /> : null}
      <span>{loading ? "Finding matches…" : "Find restaurants"}</span>
      {loading ? null : <ArrowIcon />}
    </button>
  );
}
