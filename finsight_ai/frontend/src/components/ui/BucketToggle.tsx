import { clsx } from "clsx";
import { motion } from "framer-motion";
import { TrendingUp, Landmark } from "lucide-react";

type Bucket = "investments" | "banking";

interface BucketToggleProps {
  value: Bucket;
  onChange: (b: Bucket) => void;
}

const OPTIONS: { id: Bucket; label: string; icon: React.ReactNode }[] = [
  { id: "investments", label: "Investments", icon: <TrendingUp size={13} /> },
  { id: "banking",     label: "Banking",     icon: <Landmark   size={13} /> },
];

export function BucketToggle({ value, onChange }: BucketToggleProps) {
  return (
    <div
      className="inline-flex rounded-2xl p-1 gap-0.5 relative"
      style={{
        background: "rgba(11,60,93,0.08)",
        border: "1px solid rgba(11,60,93,0.12)",
      }}
    >
      {OPTIONS.map((opt) => {
        const active = value === opt.id;
        return (
          <button
            key={opt.id}
            onClick={() => onChange(opt.id)}
            className={clsx(
              "relative flex items-center gap-2 px-4 py-2 rounded-xl text-[13px] font-semibold",
              "transition-colors duration-200 z-10",
              active ? "text-white" : "text-ocean/50 hover:text-ocean/80"
            )}
          >
            {/* Sliding coral pill */}
            {active && (
              <motion.span
                layoutId="bucket-pill"
                className="absolute inset-0 rounded-xl z-0"
                style={{
                  background: "linear-gradient(135deg, #FF7A5A 0%, #FFA38F 100%)",
                  boxShadow: "0 4px 14px rgba(255,122,90,0.35), inset 0 1px 0 rgba(255,255,255,0.20)",
                }}
                transition={{ type: "spring", stiffness: 400, damping: 32 }}
              />
            )}

            <span className="relative z-10 flex items-center gap-1.5">
              {opt.icon}
              {opt.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
