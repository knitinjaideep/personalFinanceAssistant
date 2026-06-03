import { Search, ChevronsDownUp, ChevronsUpDown } from "lucide-react";
import type { DocumentSummary } from "../../types";
import {
  STATUS_LABELS,
  institutionOptions,
  yearOptions,
  type DocumentFilterState,
} from "../../utils/documentUtils";

interface Props {
  docs: DocumentSummary[];
  filters: DocumentFilterState;
  onChange: (next: DocumentFilterState) => void;
  onExpandAll: () => void;
  onCollapseAll: () => void;
}

const darkGlass: React.CSSProperties = {
  background: "rgba(3,17,31,0.55)",
  backdropFilter: "blur(16px)",
  WebkitBackdropFilter: "blur(16px)",
  border: "1px solid rgba(34,211,238,0.12)",
  color: "rgba(255,255,255,0.80)",
};

const darkGlassSelect: React.CSSProperties = {
  ...darkGlass,
  colorScheme: "dark",
};

export function DocumentFilters({ docs, filters, onChange, onExpandAll, onCollapseAll }: Props) {
  const institutions = institutionOptions(docs);
  const years = yearOptions(docs);

  const set = (patch: Partial<DocumentFilterState>) => onChange({ ...filters, ...patch });

  return (
    <div className="flex flex-wrap items-center gap-2.5">
      {/* Search */}
      <div className="relative flex-1 min-w-[200px]">
        <Search
          size={14}
          className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
          style={{ color: "rgba(34,211,238,0.45)" }}
        />
        <input
          value={filters.search}
          onChange={(e) => set({ search: e.target.value })}
          placeholder="Search filename, account, institution…"
          className="w-full pl-9 pr-3 py-2 rounded-xl text-[13px] focus:outline-none focus:ring-2 focus:ring-cyan-400/30"
          style={{
            ...darkGlass,
            background: "rgba(3,17,31,0.55)",
          }}
        />
      </div>

      {/* Institution filter */}
      <select
        value={filters.institution}
        onChange={(e) => set({ institution: e.target.value })}
        className="px-3 py-2 rounded-xl text-[12px] font-medium focus:outline-none focus:ring-2 focus:ring-cyan-400/30"
        style={darkGlassSelect}
      >
        <option value="all">All institutions</option>
        {institutions.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      {/* Year filter */}
      <select
        value={filters.year}
        onChange={(e) => set({ year: e.target.value })}
        className="px-3 py-2 rounded-xl text-[12px] font-medium focus:outline-none focus:ring-2 focus:ring-cyan-400/30"
        style={darkGlassSelect}
      >
        <option value="all">All years</option>
        {years.map((y) => (
          <option key={y} value={String(y)}>
            {y}
          </option>
        ))}
      </select>

      {/* Status filter */}
      <select
        value={filters.status}
        onChange={(e) => set({ status: e.target.value })}
        className="px-3 py-2 rounded-xl text-[12px] font-medium focus:outline-none focus:ring-2 focus:ring-cyan-400/30"
        style={darkGlassSelect}
      >
        <option value="all">All statuses</option>
        {(["parsed", "processing", "uploaded", "failed"] as const).map((s) => (
          <option key={s} value={s}>
            {STATUS_LABELS[s]}
          </option>
        ))}
      </select>

      {/* Expand / collapse all */}
      <div className="flex items-center gap-1.5 ml-auto">
        <button
          onClick={onExpandAll}
          className="flex items-center gap-1 px-2.5 py-2 rounded-xl text-[12px] font-medium transition-colors hover:border-cyan-400/25"
          style={darkGlass}
          title="Expand all"
        >
          <ChevronsUpDown size={13} />
          Expand all
        </button>
        <button
          onClick={onCollapseAll}
          className="flex items-center gap-1 px-2.5 py-2 rounded-xl text-[12px] font-medium transition-colors hover:border-cyan-400/25"
          style={darkGlass}
          title="Collapse all"
        >
          <ChevronsDownUp size={13} />
          Collapse all
        </button>
      </div>
    </div>
  );
}
