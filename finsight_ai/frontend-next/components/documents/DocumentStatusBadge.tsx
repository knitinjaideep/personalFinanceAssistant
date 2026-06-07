"use client";

import { CheckCircle2, Loader2, Clock, XCircle, AlertTriangle, Copy, HelpCircle } from "lucide-react";
import type { LibraryStatus } from "@/lib/documentLibrary";

interface Props {
  status: LibraryStatus;
  size?: "xs" | "sm" | "md";
  showIcon?: boolean;
}

const CONFIG: Record<LibraryStatus, { label: string; color: string; bg: string; Icon: React.ElementType }> = {
  parsed:       { label: "Parsed",       color: "#3db886", bg: "rgba(61,184,134,0.12)",  Icon: CheckCircle2 },
  processing:   { label: "Processing",   color: "#22d3ee", bg: "rgba(34,211,238,0.10)",  Icon: Loader2 },
  uploaded:     { label: "Uploaded",     color: "#5FA8D3", bg: "rgba(95,168,211,0.12)",  Icon: Clock },
  failed:       { label: "Failed",       color: "#E45757", bg: "rgba(228,87,87,0.12)",   Icon: XCircle },
  needs_review: { label: "Needs Review", color: "#c89a00", bg: "rgba(200,154,0,0.12)",   Icon: AlertTriangle },
  duplicate:    { label: "Duplicate",    color: "#9B59B6", bg: "rgba(155,89,182,0.12)",  Icon: Copy },
  unknown:      { label: "Unknown",      color: "#94a3b8", bg: "rgba(148,163,184,0.10)", Icon: HelpCircle },
};

const SIZE = {
  xs: { text: "text-[9.5px]",  px: "px-1.5 py-0.5", icon: 9,  gap: "gap-0.5" },
  sm: { text: "text-[10.5px]", px: "px-2 py-0.5",   icon: 11, gap: "gap-1" },
  md: { text: "text-[12px]",   px: "px-2.5 py-1",   icon: 12, gap: "gap-1.5" },
};

export default function DocumentStatusBadge({ status, size = "sm", showIcon = true }: Props) {
  const cfg = CONFIG[status] ?? CONFIG.unknown;
  const sz = SIZE[size];
  return (
    <span
      className={`inline-flex items-center ${sz.gap} ${sz.px} ${sz.text} rounded-full font-semibold shrink-0`}
      style={{ background: cfg.bg, color: cfg.color }}
    >
      {showIcon && (
        <cfg.Icon size={sz.icon} className={status === "processing" ? "animate-spin" : ""} />
      )}
      {cfg.label}
    </span>
  );
}
