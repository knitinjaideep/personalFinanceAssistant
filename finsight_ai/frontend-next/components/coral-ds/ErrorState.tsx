import { AlertTriangle } from "lucide-react";

interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
  compact?: boolean;
}

export default function ErrorState({ title = "Something went wrong", message, onRetry, compact = false }: ErrorStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center text-center rounded-2xl ${compact ? "py-10 px-6" : "py-20 px-8"}`}
      style={{ background: "var(--status-danger-soft)", border: "1px solid var(--status-danger-soft)" }}
    >
      <div
        className="flex items-center justify-center rounded-2xl mb-5"
        style={{ width: compact ? 48 : 64, height: compact ? 48 : 64, background: "var(--card-bg)", border: "1px solid var(--status-danger-soft)" }}
      >
        <AlertTriangle size={compact ? 22 : 28} style={{ color: "var(--status-danger)" }} />
      </div>

      <h3 className={compact ? "card-title-lg mb-2" : "section-title mb-3"}>{title}</h3>

      {message && (
        <p className={`${compact ? "small-text" : "body-text"} max-w-sm`} style={{ color: "var(--text-secondary)" }}>
          {message}
        </p>
      )}

      {onRetry && (
        <button onClick={onRetry} className="mt-6 px-5 py-2.5 rounded-2xl text-sm font-semibold btn-glass transition-all">
          Try again
        </button>
      )}
    </div>
  );
}
