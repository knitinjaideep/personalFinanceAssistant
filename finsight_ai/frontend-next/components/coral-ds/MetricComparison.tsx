interface MetricComparisonProps {
  label: string;
  actual: string;
  target: string;
  className?: string;
}

export default function MetricComparison({ label, actual, target, className }: MetricComparisonProps) {
  return (
    <div className={className}>
      <p className="eyebrow-text mb-1">{label}</p>
      <div className="flex items-baseline gap-2">
        <span className="metric-value-sm tabular-nums" style={{ color: "var(--text-strong)" }}>
          {actual}
        </span>
        <span className="small-text tabular-nums" style={{ color: "var(--text-muted)" }}>
          / {target} target
        </span>
      </div>
    </div>
  );
}
