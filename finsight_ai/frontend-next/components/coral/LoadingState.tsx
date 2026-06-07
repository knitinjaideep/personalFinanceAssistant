interface LoadingStateProps {
  rows?: number;
  columns?: number;
  message?: string;
  compact?: boolean;
}

function SkeletonRow() {
  return (
    <div className="flex items-center gap-4 p-5 rounded-2xl" style={{ background: "var(--panel-bg)", border: "1px solid var(--border-subtle)" }}>
      <div className="skeleton w-10 h-10 rounded-2xl shrink-0" />
      <div className="flex-1 space-y-2">
        <div className="skeleton h-4 w-3/5 rounded-md" />
        <div className="skeleton h-3 w-2/5 rounded-md" />
      </div>
      <div className="skeleton h-6 w-16 rounded-lg" />
    </div>
  );
}

function SkeletonCard() {
  return (
    <div className="glass rounded-3xl p-6 space-y-3">
      <div className="skeleton h-3 w-24 rounded-md" />
      <div className="skeleton h-9 w-32 rounded-lg" />
      <div className="skeleton h-3 w-20 rounded-md" />
    </div>
  );
}

export default function LoadingState({
  rows = 3,
  columns = 3,
  message,
  compact = false,
}: LoadingStateProps) {
  if (compact) {
    return (
      <div className="space-y-3">
        {Array.from({ length: rows }).map((_, i) => (
          <SkeletonRow key={i} />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Metric skeleton row */}
      <div className={`grid gap-4 grid-cols-2 md:grid-cols-${Math.min(columns, 4)}`}>
        {Array.from({ length: columns }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>

      {/* List skeleton */}
      <div className="space-y-3">
        {Array.from({ length: rows }).map((_, i) => (
          <SkeletonRow key={i} />
        ))}
      </div>

      {message && (
        <p className="small-text text-center" style={{ color: "var(--text-dim)" }}>{message}</p>
      )}
    </div>
  );
}
