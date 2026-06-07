import { Upload, FolderUp, Wand2, Lock } from "lucide-react";
import { motion } from "framer-motion";

interface Props {
  onUpload: () => void;
  onBulkUpload: () => void;
  onReprocessMissing: () => void;
  reprocessingMissing?: boolean;
  docCount: number;
}

export function FinancialLibraryHeader({
  onUpload,
  onBulkUpload,
  onReprocessMissing,
  reprocessingMissing = false,
  docCount,
}: Props) {
  const glassBtn =
    "flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl coral-nav-text font-semibold transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]";
  const glassStyle: React.CSSProperties = {
    background: "var(--btn-glass-bg)",
    backdropFilter: "blur(8px)",
    WebkitBackdropFilter: "blur(8px)",
    border: "1px solid var(--btn-glass-border)",
    color: "var(--btn-glass-color)",
  };

  return (
    <section
      className="relative overflow-hidden shrink-0 mx-6 mt-8 mb-5 rounded-[28px]"
      style={{
        background: "rgba(3,17,31,0.65)",
        backdropFilter: "blur(24px)",
        WebkitBackdropFilter: "blur(24px)",
        border: "1px solid rgba(34,211,238,0.18)",
        boxShadow: "0 24px 80px rgba(0,0,0,0.32)",
      }}
    >
      {/* Subtle gradient overlay */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 60% 80% at 90% 50%, rgba(34,211,238,0.06) 0%, transparent 70%)",
        }}
      />

      {/* Glitter stars */}
      <span
        aria-hidden
        className="absolute w-1 h-1 rounded-full opacity-70"
        style={{ background: "rgba(34,211,238,0.85)", top: "22%", left: "55%" }}
      />
      <span
        aria-hidden
        className="absolute w-1.5 h-1.5 rounded-full opacity-50"
        style={{ background: "rgba(255,122,90,0.70)", top: "70%", left: "80%" }}
      />
      <span
        aria-hidden
        className="absolute w-1 h-1 rounded-full opacity-60"
        style={{ background: "rgba(255,209,102,0.80)", top: "40%", left: "92%" }}
      />

      <div className="relative flex flex-col sm:flex-row items-start sm:items-center justify-between gap-5 p-7">
        {/* Left: title block */}
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1">
            {/* Document icon */}
            <div
              className="flex items-center justify-center w-9 h-9 rounded-2xl shrink-0"
              style={{
                background: "rgba(34,211,238,0.10)",
                border: "1px solid rgba(34,211,238,0.20)",
              }}
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="rgba(34,211,238,0.85)"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
                <polyline points="10 9 9 9 8 9" />
              </svg>
            </div>
            <h1
              className="text-2xl xl:text-3xl font-extrabold tracking-tight leading-none"
              style={{ color: "var(--text-primary)" }}
            >
              Financial Library
            </h1>
          </div>

          <p
            className="coral-muted font-medium leading-relaxed mb-2 pl-11"
            style={{ color: "var(--text-muted)" }}
          >
            {docCount > 0
              ? `${docCount} statement${docCount !== 1 ? "s" : ""} · organized locally by institution, account, and time.`
              : "Your statements, organized locally by institution, account, and time."}
          </p>

          {/* Privacy line */}
          <div className="flex items-center gap-1.5 pl-11">
            <Lock size={11} style={{ color: "rgba(34,211,238,0.60)" }} />
            <span
              className="text-xs font-medium"
              style={{ color: "rgba(34,211,238,0.60)" }}
            >
              All files stay on your device.
            </span>
          </div>
        </div>

        {/* Right: action buttons */}
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <button
            onClick={onReprocessMissing}
            disabled={reprocessingMissing}
            className={glassBtn + " disabled:opacity-50"}
            style={{
              ...glassStyle,
              background: "rgba(255,122,90,0.08)",
              border: "1px solid rgba(255,122,90,0.22)",
              color: "#FF9B85",
            }}
            title="Reprocess documents with missing data"
          >
            <Wand2 size={13} />
            Reprocess Missing Data
          </button>

          <button onClick={onBulkUpload} className={glassBtn} style={glassStyle}>
            <FolderUp size={13} />
            Bulk Upload
          </button>

          <motion.button
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            onClick={onUpload}
            className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl coral-button-text font-semibold text-white"
            style={{
              background: "linear-gradient(135deg, #FF7A5A, #FFA38F)",
              boxShadow: "0 4px 18px rgba(255,122,90,0.40)",
            }}
          >
            <Upload size={13} />
            Upload
          </motion.button>
        </div>
      </div>
    </section>
  );
}
