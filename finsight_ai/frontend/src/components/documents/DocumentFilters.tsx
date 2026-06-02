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

const selectStyle: React.CSSProperties = {
  background: "rgba(255,255,255,0.9)",
  border: "1px solid rgba(205,237,246,0.7)",
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
          className="absolute left-3 top-1/2 -translate-y-1/2 text-ocean/35 pointer-events-none"
        />
        <input
          value={filters.search}
          onChange={(e) => set({ search: e.target.value })}
          placeholder="Search filename, account, institution…"
          className="w-full pl-9 pr-3 py-2 rounded-xl text-[13px] text-ocean-deep placeholder:text-ocean/30 focus:outline-none focus:ring-2 focus:ring-ocean-sea/30"
          style={selectStyle}
        />
      </div>

      {/* Institution filter */}
      <select
        value={filters.institution}
        onChange={(e) => set({ institution: e.target.value })}
        className="px-3 py-2 rounded-xl text-[12px] font-medium text-ocean-deep focus:outline-none focus:ring-2 focus:ring-ocean-sea/30"
        style={selectStyle}
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
        className="px-3 py-2 rounded-xl text-[12px] font-medium text-ocean-deep focus:outline-none focus:ring-2 focus:ring-ocean-sea/30"
        style={selectStyle}
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
        className="px-3 py-2 rounded-xl text-[12px] font-medium text-ocean-deep focus:outline-none focus:ring-2 focus:ring-ocean-sea/30"
        style={selectStyle}
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
          className="flex items-center gap-1 px-2.5 py-2 rounded-xl text-[12px] font-medium text-ocean/60 hover:text-ocean transition-colors"
          style={selectStyle}
          title="Expand all"
        >
          <ChevronsUpDown size={13} />
          Expand all
        </button>
        <button
          onClick={onCollapseAll}
          className="flex items-center gap-1 px-2.5 py-2 rounded-xl text-[12px] font-medium text-ocean/60 hover:text-ocean transition-colors"
          style={selectStyle}
          title="Collapse all"
        >
          <ChevronsDownUp size={13} />
          Collapse all
        </button>
      </div>
    </div>
  );
}
