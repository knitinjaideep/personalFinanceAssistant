import { type ReactNode } from "react";
import { clsx } from "clsx";

interface CardProps {
  children: ReactNode;
  className?: string;
  variant?: "default" | "ocean" | "coral" | "sand";
  padding?: "none" | "sm" | "md" | "lg";
  hover?: boolean;
}

const variantClasses = {
  default: "bg-white border border-ocean-100",
  ocean: "bg-ocean-deep text-white border border-ocean-700",
  coral: "bg-coral-50 border border-coral-100",
  sand: "bg-sand-50 border border-sand-100",
};

const paddingClasses = {
  none: "",
  sm: "p-4",
  md: "p-5",
  lg: "p-6",
};

export function Card({
  children,
  className,
  variant = "default",
  padding = "md",
  hover = false,
}: CardProps) {
  return (
    <div
      className={clsx(
        "rounded-2xl shadow-soft",
        variantClasses[variant],
        paddingClasses[padding],
        hover && "transition-all duration-200 hover:shadow-card hover:-translate-y-0.5",
        className
      )}
    >
      {children}
    </div>
  );
}
