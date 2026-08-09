import { clsx } from "clsx";

interface SkeletonStateProps {
  variant?: "text" | "block" | "card";
  width?: string;
  height?: string;
  className?: string;
  count?: number;
}

const SHAPE_CLASS: Record<NonNullable<SkeletonStateProps["variant"]>, string> = {
  text: "rounded-md",
  block: "rounded-lg",
  card: "rounded-2xl",
};

const DEFAULT_HEIGHT: Record<NonNullable<SkeletonStateProps["variant"]>, string> = {
  text: "0.9rem",
  block: "2.5rem",
  card: "8rem",
};

/** Generalizes the ad hoc `.skeleton` class usage (previously duplicated inline in MetricCard). */
export default function SkeletonState({ variant = "block", width, height, className, count = 1 }: SkeletonStateProps) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className={clsx("skeleton", SHAPE_CLASS[variant], className)}
          style={{ width: width ?? "100%", height: height ?? DEFAULT_HEIGHT[variant] }}
        />
      ))}
    </>
  );
}
