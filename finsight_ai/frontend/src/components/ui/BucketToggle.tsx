import { clsx } from "clsx";
import { motion, AnimatePresence } from "framer-motion";

type Bucket = "investments" | "banking";

interface BucketToggleProps {
  value: Bucket;
  onChange: (b: Bucket) => void;
}

const OPTIONS: { id: Bucket; label: string; emoji: string }[] = [
  { id: "investments", label: "Investments", emoji: "📈" },
  { id: "banking",     label: "Banking",     emoji: "🏦" },
];

export function BucketToggle({ value, onChange }: BucketToggleProps) {
  return (
    <div
      className="inline-flex rounded-2xl p-1 gap-1 relative"
      style={{
        background: "rgba(11,60,93,0.12)",
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
        border: "1px solid rgba(255,255,255,0.15)",
      }}
    >
      {OPTIONS.map((opt) => {
        const active = value === opt.id;
        return (
          <button
            key={opt.id}
            onClick={() => onChange(opt.id)}
            className={clsx(
              "relative px-4 py-2 rounded-xl text-sm font-semibold transition-colors duration-200 z-10",
              active ? "text-ocean-deep" : "text-white/55 hover:text-white/80"
            )}
          >
            {/* Sliding pill background */}
            <AnimatePresence>
              {active && (
                <motion.span
                  layoutId="bucket-pill"
                  className="absolute inset-0 rounded-xl z-0"
                  style={{
                    background: "rgba(255,255,255,0.92)",
                    boxShadow: "0 2px 12px rgba(11,60,93,0.15)",
                  }}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                />
              )}
            </AnimatePresence>

            <span className="relative z-10 flex items-center gap-1.5">
              <span className="text-xs">{opt.emoji}</span>
              {opt.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
