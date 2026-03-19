import { clsx } from "clsx";

type Bucket = "investments" | "banking";

interface BucketToggleProps {
  value: Bucket;
  onChange: (b: Bucket) => void;
}

const OPTIONS: { id: Bucket; label: string }[] = [
  { id: "investments", label: "Investments" },
  { id: "banking", label: "Banking" },
];

export function BucketToggle({ value, onChange }: BucketToggleProps) {
  return (
    <div className="inline-flex bg-ocean-50 rounded-xl p-1 gap-1">
      {OPTIONS.map((opt) => (
        <button
          key={opt.id}
          onClick={() => onChange(opt.id)}
          className={clsx(
            "px-4 py-1.5 rounded-lg text-sm font-medium transition-all duration-200",
            value === opt.id
              ? "bg-white text-ocean-deep shadow-soft"
              : "text-ocean-DEFAULT/60 hover:text-ocean-DEFAULT"
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
