import type { ReactNode } from "react";
import { ErrorIcon, InfoIcon, SuccessIcon, WarningIcon } from "./icons";

type BannerTone = "success" | "info" | "warning" | "error";

const TONE_CLASS: Record<BannerTone, string> = {
  success: "border-success-border bg-success-bg text-success",
  info: "border-info-border bg-info-bg text-info",
  warning: "border-warning-border bg-warning-bg text-warning",
  error: "border-danger-border bg-danger-bg text-danger",
};

const TONE_ICON: Record<BannerTone, ReactNode> = {
  success: <SuccessIcon />,
  info: <InfoIcon />,
  warning: <WarningIcon />,
  error: <ErrorIcon />,
};

type StatusBannerProps = {
  tone: BannerTone;
  label: string;
  children: ReactNode;
};

export function StatusBanner({ tone, label, children }: StatusBannerProps) {
  return (
    <div
      role={tone === "error" || tone === "warning" ? "alert" : "status"}
      className={`flex items-center gap-3 rounded-xl border px-4 py-3 text-xs shadow-[0_1px_2px_rgba(28,28,28,0.06)] ${TONE_CLASS[tone]}`}
    >
      {TONE_ICON[tone]}
      <p className="leading-relaxed">
        <strong>{label}: </strong>
        {children}
      </p>
    </div>
  );
}
