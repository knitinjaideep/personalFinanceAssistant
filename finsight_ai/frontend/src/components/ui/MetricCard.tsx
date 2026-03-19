import { type ReactNode } from "react";
import { clsx } from "clsx";
import { Card } from "./Card";

interface MetricCardProps {
  label: string;
  value: string | number;
  icon: ReactNode;
  accent?: "coral" | "ocean" | "positive" | "highlight";
  className?: string;
}

const accentClasses = {
  coral: "text-coral",
  ocean: "text-ocean",
  positive: "text-positive",
  highlight: "text-highlight",
};

const iconBgClasses = {
  coral: "bg-coral-50 text-coral",
  ocean: "bg-ocean-50 text-ocean",
  positive: "bg-positive/10 text-positive",
  highlight: "bg-highlight/20 text-highlight",
};

export function MetricCard({
  label,
  value,
  icon,
  accent = "ocean",
  className,
}: MetricCardProps) {
  return (
    <Card hover className={clsx("flex flex-col gap-3", className)}>
      <div className="flex items-start justify-between">
        <span className="text-xs font-medium text-ocean-DEFAULT/60 uppercase tracking-wider">
          {label}
        </span>
        <div className={clsx("p-2 rounded-xl", iconBgClasses[accent])}>
          {icon}
        </div>
      </div>
      <p className={clsx("text-3xl font-bold tracking-tight", accentClasses[accent])}>
        {typeof value === "number" ? value.toLocaleString() : value}
      </p>
    </Card>
  );
}
