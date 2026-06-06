import { Search, ChevronsDownUp, ChevronsUpDown } from "lucide-react";
import type { DocumentSummary } from "../../types";
import {
  STATUS_LABELS, institutionOptions, yearOptions,
  type DocumentFilterState,
} from "../../utils/documentUtils";
import { useAppStore } from "../../store/appStore";

interface Props {
  docs: DocumentSummary[];
  filters: DocumentFilterState;
  onChange: (next: DocumentFilterState) => void;
  onExpandAll: () => void;
  onCollapseAll: () => void;
}

export function DocumentFilters({ docs, filters, onChange, onExpandAll, onCollapseAll }: Props) {
  const theme = useAppStore((s) => s.theme);
  const isLight = theme === "light";

  const institutions = institutionOptions(docs);
  const years = yearOptions(docs);
  const set = (patch: Partial<DocumentFilterState>) => onChange({ ...filters, ...patch });

  const inputStyle: React.CSSProperties = {
    background: "var(--panel-bg)",
    backdropFilter: "blur(16px)",
    WebkitBackdropFilter: "blur(16px)",
    border: "1px solid var(--panel-border-accent)",
    color: "var(--text-primary)",
    colorScheme: isLight ? "light" : "dark",
  };

  const btnStyle: React.CSSProperties = {
    background: "var(--panel-bg)",
    backdropFilter: "blur(16px)",
    WebkitBackdropFilter: "blur(16px)",
    border: "1px solid var(--panel-border-accent)",
    color: "var(--text-secondary)",
  };

  return (
    <div className="flex flex-wrap items-center gap-2.5">
      {/* Search */}
      <div className="relative flex-1 min-w-[200px]">
        <Search
          size={14}
          className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
          style={{ color: "var(--border-accent)" }}
        />
        <input
          value={filters.search}
          onChange={(e) => set({ search: e.target.value })}
          placeholder="Search filename, account, institution…"
          className="w-full pl-9 pr-3 py-2 rounded-xl text-[13px] focus:outline-none focus:ring-2"
          style={{ ...inputStyle, outlineColor: "var(--focus-ring)" }}
        />
      </div>

      {/* Institution filter */}
      <select
        value={filters.institution}
        onChange={(e) => set({ institution: e.target.value })}
        className="px-3 py-2 rounded-xl text-[12px] font-medium focus:outline-none focus:ring-2"
        style={inputStyle}
      >
        <option value="all">All institutions</option>
        {institutions.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>

      {/* Year filter */}
      <select
        value={filters.year}
        onChange={(e) => set({ year: e.target.value })}
        className="px-3 py-2 rounded-xl text-[12px] font-medium focus:outline-none focus:ring-2"
        style={inputStyle}
      >
        <option value="all">All years</option>
        {years.map((y) => (
          <option key={y} value={String(y)}>{y}</option>
        ))}
      </select>

      {/* Status filter */}
      <select
        value={filters.status}
        onChange={(e) => set({ status: e.target.value })}
        className="px-3 py-2 rounded-xl text-[12px] font-medium focus:outline-none focus:ring-2"
        style={inputStyle}
      >
        <option value="all">All statuses</option>
        {(["parsed", "processing", "uploaded", "failed"] as const).map((s) => (
          <option key={s} value={s}>{STATUS_LABELS[s]}</option>
        ))}
      </select>

      {/* Expand / collapse all */}
      <div className="flex items-center gap-1.5 ml-auto">
        <button
          onClick={onExpandAll}
          className="flex items-center gap-1 px-2.5 py-2 rounded-xl text-[12px] font-medium transition-all hover:scale-[1.02]"
          style={btnStyle}
          title="Expand all"
        >
          <ChevronsUpDown size={13} />
          Expand all
        </button>
        <button
          onClick={onCollapseAll}
          className="flex items-center gap-1 px-2.5 py-2 rounded-xl text-[12px] font-medium transition-all hover:scale-[1.02]"
          style={btnStyle}
          title="Collapse all"
        >
          <ChevronsDownUp size={13} />
          Collapse all
        </button>
      </div>
    </div>
  );
}
