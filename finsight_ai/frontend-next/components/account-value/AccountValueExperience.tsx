"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  ChevronDown,
  Landmark,
  LineChart as LineChartIcon,
  Table2,
  TrendingUp,
  WalletCards,
} from "lucide-react";
import {
  type AccountValueDataset,
  type AccountValuePoint,
  type AccountValueSeries,
  formatMonthLabel,
} from "@/lib/accountValue";
import { formatCompactCurrency, formatCurrency } from "@/lib/utils";

const COLORS = ["#2563eb", "#149a6a", "#6d4de8", "#ff6f3c", "#0ea5e9", "#f59e0b"];

export type AccountValueViewMode = "line" | "table";

interface AccountMeta {
  accountId: string;
  purpose?: string | null;
  classification?: string | null;
  shareOfTotal?: number | null;
  holdingsSummary?: string | null;
}

function colorFor(index: number) {
  return COLORS[index % COLORS.length];
}

function deltaLabel(value: number | null, compact = false) {
  if (value === null) return "No prior month";
  const amount = compact ? formatCompactCurrency(Math.abs(value)) : formatCurrency(Math.abs(value));
  return `${value >= 0 ? "+" : "-"}${amount}`;
}

function percentLabel(value: number | null) {
  if (value === null) return "-";
  return `${value >= 0 ? "+" : "-"}${Math.abs(value).toFixed(1)}%`;
}

function monthValue(account: AccountValueSeries, month: string) {
  return account.points.find((point) => point.month === month)?.value ?? null;
}

function Sparkline({ points, color }: { points: AccountValuePoint[]; color: string }) {
  if (points.length < 2) {
    return <div className="h-12 rounded-xl" style={{ background: "var(--panel-bg-alt)" }} />;
  }
  const width = 140;
  const height = 48;
  const values = points.slice(-8).map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const path = values.map((value, index) => {
    const x = (index / Math.max(values.length - 1, 1)) * width;
    const y = height - ((value - min) / range) * (height - 10) - 5;
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-12 w-full" aria-hidden="true">
      <path d={path} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d={`${path} L${width},${height} L0,${height} Z`} fill={color} opacity="0.08" />
    </svg>
  );
}

function AccountIcon({ domain, color }: { domain: "banking" | "investments"; color: string }) {
  const Icon = domain === "banking" ? WalletCards : TrendingUp;
  return (
    <span
      className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl"
      style={{ background: `${color}18`, color, border: `1px solid ${color}22` }}
    >
      <Icon size={19} />
    </span>
  );
}

export function AccountValueViewToggle({
  value,
  onChange,
}: {
  value: AccountValueViewMode;
  onChange: (value: AccountValueViewMode) => void;
}) {
  return (
    <div
      className="inline-flex rounded-2xl p-1"
      style={{ background: "var(--panel-bg-alt)", border: "1px solid var(--border-subtle)" }}
      aria-label="Account value view"
    >
      {[
        { value: "line" as const, label: "Line chart", icon: LineChartIcon },
        { value: "table" as const, label: "Table view", icon: Table2 },
      ].map((option) => {
        const Icon = option.icon;
        const active = value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className="inline-flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
            style={{
              color: active ? "var(--financial-needs)" : "var(--text-muted)",
              background: active ? "var(--accent-soft)" : "transparent",
              boxShadow: active ? "0 4px 14px var(--card-shadow)" : "none",
            }}
            aria-pressed={active}
          >
            <Icon size={14} />
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export function AccountValueSummaryCard({
  account,
  color,
  selected,
  onSelect,
}: {
  account: AccountValueSeries;
  color: string;
  selected: boolean;
  onSelect: () => void;
}) {
  const deltaPositive = (account.change ?? 0) >= 0;
  return (
    <button
      type="button"
      onClick={onSelect}
      data-account-value-card="true"
      aria-label={`${selected ? "Collapse" : "Expand"} ${account.accountName} account details`}
      aria-expanded={selected}
      className="group min-h-[138px] rounded-3xl p-5 text-left transition focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
      style={{
        background: "var(--card-bg)",
        border: selected ? `1px solid ${color}88` : "1px solid var(--border-subtle)",
        boxShadow: selected
          ? `0 18px 44px ${color}1f`
          : "var(--panel-shadow)",
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <AccountIcon domain={account.domain} color={color} />
          <div className="min-w-0">
            <p className="truncate text-sm font-bold" style={{ color: "var(--text-primary)" }}>
              {account.accountName}
            </p>
            <p className="mt-1 truncate text-xs" style={{ color: "var(--text-muted)" }}>
              {account.institution}
            </p>
          </div>
        </div>
        <ChevronDown
          size={17}
          className="mt-1 shrink-0 transition-transform duration-200 group-hover:translate-y-0.5"
          style={{ color, transform: selected ? "rotate(180deg)" : "rotate(0deg)" }}
          aria-hidden="true"
        />
      </div>

      <div className="mt-4 grid grid-cols-[minmax(0,1fr)_118px] items-end gap-3">
        <div className="min-w-0">
          <p className="text-2xl font-black tabular-nums tracking-normal" style={{ color: "var(--text-primary)" }}>
            {account.latest ? formatCurrency(account.latest.value) : "-"}
          </p>
          <p
            className="mt-2 text-sm font-semibold tabular-nums"
            style={{ color: deltaPositive ? "#149a6a" : "#d84b36" }}
          >
            {deltaLabel(account.change, true)}
            <span className="ml-2 font-medium" style={{ color: "var(--text-muted)" }}>
              vs {account.previous ? formatMonthLabel(account.previous.month) : "prior month"}
            </span>
          </p>
        </div>
        <Sparkline points={account.points} color={color} />
      </div>
    </button>
  );
}

function chartRows(dataset: AccountValueDataset) {
  return dataset.months.map((month) => {
    const row: Record<string, string | number | null> = {
      month,
      monthLabel: formatMonthLabel(month),
    };
    for (const account of dataset.accounts) {
      row[account.accountId] = monthValue(account, month);
    }
    return row;
  });
}

export function AccountValueTrendChart({
  dataset,
  height = 360,
  selectedAccountId,
}: {
  dataset: AccountValueDataset;
  height?: number;
  selectedAccountId?: string | null;
}) {
  const rows = useMemo(() => chartRows(dataset), [dataset]);
  if (rows.length === 0) {
    return (
      <div
        className="flex h-72 items-center justify-center rounded-3xl text-sm"
        style={{ background: "var(--panel-bg-alt)", color: "var(--text-muted)" }}
      >
        No account value snapshots in this period.
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <LineChart data={rows} margin={{ top: 18, right: 18, left: 8, bottom: 10 }}>
          <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="4 4" vertical={false} />
          <XAxis
            dataKey="monthLabel"
            tick={{ fill: "var(--chart-axis)", fontSize: 12 }}
            tickLine={false}
            axisLine={false}
            minTickGap={24}
          />
          <YAxis
            tickFormatter={(value) => formatCompactCurrency(Number(value))}
            tick={{ fill: "var(--chart-axis)", fontSize: 12 }}
            tickLine={false}
            axisLine={false}
            width={76}
          />
          <Tooltip
            formatter={(value) => [formatCurrency(Number(value)), "Value"]}
            labelStyle={{ color: "var(--text-primary)", fontWeight: 700 }}
            itemStyle={{ color: "var(--text-secondary)" }}
            contentStyle={{
              background: "var(--card-bg)",
              borderRadius: 16,
              border: "1px solid var(--border-subtle)",
              boxShadow: "var(--panel-shadow)",
            }}
          />
          {dataset.accounts.map((account, index) => {
            const highlighted = !selectedAccountId || selectedAccountId === account.accountId;
            return (
              <Line
                key={account.accountId}
                type="monotone"
                dataKey={account.accountId}
                name={account.accountName}
                connectNulls={false}
                stroke={colorFor(index)}
                strokeWidth={highlighted ? 2.8 : 1.8}
                opacity={highlighted ? 1 : 0.26}
                dot={{ r: highlighted ? 3.5 : 2.5, strokeWidth: 2, fill: "#fff" }}
                activeDot={{ r: 6, strokeWidth: 2 }}
              />
            );
          })}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function AccountValueTable({ dataset }: { dataset: AccountValueDataset }) {
  if (dataset.months.length === 0) {
    return (
      <div
        className="rounded-3xl p-8 text-center text-sm"
        style={{ background: "var(--panel-bg-alt)", color: "var(--text-muted)" }}
      >
        No account value snapshots in this period.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-3xl border border-slate-200/80 bg-white/80">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="bg-slate-50/80 text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="sticky left-0 bg-slate-50/95 px-5 py-3 font-bold">Month</th>
            {dataset.accounts.map((account) => (
              <th key={account.accountId} className="whitespace-nowrap px-5 py-3 font-bold">
                {account.accountName}
              </th>
            ))}
            <th className="whitespace-nowrap px-5 py-3 font-bold">Total</th>
          </tr>
        </thead>
        <tbody>
          {dataset.months.map((month) => {
            const values = dataset.accounts.map((account) => monthValue(account, month));
            const total = values.reduce<number>((sum, value) => sum + (value ?? 0), 0);
            return (
              <tr key={month} className="border-t border-slate-200/70">
                <td className="sticky left-0 bg-white/95 px-5 py-3 font-semibold text-slate-800">
                  {formatMonthLabel(month)}
                </td>
                {values.map((value, index) => (
                  <td key={`${month}-${dataset.accounts[index].accountId}`} className="whitespace-nowrap px-5 py-3 tabular-nums text-slate-700">
                    {value === null ? "-" : formatCurrency(value)}
                  </td>
                ))}
                <td className="whitespace-nowrap px-5 py-3 font-bold tabular-nums text-slate-900">
                  {formatCurrency(total)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function AccountMiniTrend({ account, color }: { account: AccountValueSeries; color: string }) {
  const fillId = `account-fill-${account.accountId.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
  const rows = account.points.slice(-12).map((point) => ({
    monthLabel: formatMonthLabel(point.month),
    value: point.value,
  }));
  if (rows.length < 2) return <Sparkline points={account.points} color={color} />;
  return (
    <div className="h-52 w-full">
      <ResponsiveContainer>
        <AreaChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.18} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="4 4" vertical={false} />
          <XAxis dataKey="monthLabel" tick={{ fill: "var(--chart-axis)", fontSize: 11 }} tickLine={false} axisLine={false} />
          <YAxis tickFormatter={(value) => formatCompactCurrency(Number(value))} tick={{ fill: "var(--chart-axis)", fontSize: 11 }} tickLine={false} axisLine={false} width={64} />
          <Tooltip
            formatter={(value) => [formatCurrency(Number(value)), account.accountName]}
            labelStyle={{ color: "var(--text-primary)", fontWeight: 700 }}
            itemStyle={{ color: "var(--text-secondary)" }}
            contentStyle={{
              background: "var(--card-bg)",
              border: "1px solid var(--border-subtle)",
              borderRadius: 14,
              boxShadow: "var(--panel-shadow)",
            }}
          />
          <Area type="monotone" dataKey="value" stroke={color} strokeWidth={2.5} fill={`url(#${fillId})`} dot={{ r: 3, fill: "#fff", stroke: color, strokeWidth: 2 }} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ExpandedAccountDetail({
  account,
  color,
  meta,
}: {
  account: AccountValueSeries | null;
  color: string;
  meta?: AccountMeta | null;
}) {
  const prefersReducedMotion = useReducedMotion();
  if (!account) return null;
  const latest = account.latest?.value ?? null;
  const previous = account.previous?.value ?? null;
  const rows = account.points.slice(-12).map((point, index, points) => {
    const previousPoint = index > 0 ? points[index - 1] : null;
    const change = previousPoint ? point.value - previousPoint.value : null;
    return { ...point, change };
  });

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={account.accountId}
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{
          duration: prefersReducedMotion ? 0 : 0.22,
          ease: [0.4, 0, 0.2, 1],
        }}
        className="rounded-[28px] p-5 md:p-6"
        style={{
          background: "linear-gradient(180deg, var(--panel-bg-alt), var(--panel-bg))",
          border: `1px solid ${color}33`,
          boxShadow: "var(--panel-shadow)",
          color: "var(--text-primary)",
        }}
      >
        <div className="grid gap-5 xl:grid-cols-[minmax(0,0.95fr)_minmax(420px,1.05fr)]">
          <div>
            <div className="flex items-start gap-3">
              <AccountIcon domain={account.domain} color={color} />
              <div>
                <h3 className="text-xl font-black tracking-normal text-slate-950">{account.accountName}</h3>
                <p className="mt-1 text-sm text-slate-600">
                  {account.institution} · {account.accountType.replace(/_/g, " ")}
                </p>
              </div>
            </div>

            <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                ["Current Value", latest === null ? "-" : formatCurrency(latest)],
                ["Previous Month", previous === null ? "-" : formatCurrency(previous)],
                ["Change", deltaLabel(account.change)],
                ["Change %", percentLabel(account.changePct)],
              ].map(([label, value]) => (
                <div key={label} className="rounded-2xl border border-slate-200/80 bg-white/80 p-4">
                  <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">{label}</p>
                  <p className="mt-2 text-lg font-black tabular-nums text-slate-950">{value}</p>
                </div>
              ))}
            </div>

            <div className="mt-5 grid gap-3 text-sm text-slate-600 sm:grid-cols-2">
              <div className="rounded-2xl bg-white/70 p-4">
                <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Latest Statement</p>
                <p className="mt-1 font-semibold text-slate-800">
                  {account.latestStatementMonth ? formatMonthLabel(account.latestStatementMonth) : "Unavailable"}
                </p>
              </div>
              <div className="rounded-2xl bg-white/70 p-4">
                <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Classification</p>
                <p className="mt-1 font-semibold text-slate-800">
                  {meta?.classification ?? account.accountType.replace(/_/g, " ")}
                </p>
              </div>
              {meta?.purpose && (
                <div className="rounded-2xl bg-white/70 p-4 sm:col-span-2">
                  <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Purpose</p>
                  <p className="mt-1 font-semibold text-slate-800">{meta.purpose}</p>
                </div>
              )}
              {meta?.shareOfTotal !== null && meta?.shareOfTotal !== undefined && (
                <div className="rounded-2xl bg-white/70 p-4">
                  <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Portfolio Share</p>
                  <p className="mt-1 font-semibold text-slate-800">{meta.shareOfTotal.toFixed(1)}%</p>
                </div>
              )}
              {meta?.holdingsSummary && (
                <div className="rounded-2xl bg-white/70 p-4">
                  <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Holdings</p>
                  <p className="mt-1 font-semibold text-slate-800">{meta.holdingsSummary}</p>
                </div>
              )}
            </div>
          </div>

          <div className="space-y-5">
            <div>
              <div className="mb-3 flex items-center justify-between gap-3">
                <h4 className="text-base font-black text-slate-950">Account Trend</h4>
                <span className="text-xs font-semibold text-slate-500">Monthly snapshots</span>
              </div>
              <AccountMiniTrend account={account} color={color} />
            </div>

            <div>
              <h4 className="mb-3 text-base font-black text-slate-950">Recent Monthly Values</h4>
              <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white/82">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-4 py-3">Month</th>
                      <th className="px-4 py-3">Value</th>
                      <th className="px-4 py-3">Change</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.month} className="border-t border-slate-200/70">
                        <td className="px-4 py-3 font-semibold text-slate-800">{formatMonthLabel(row.month)}</td>
                        <td className="px-4 py-3 tabular-nums text-slate-700">{formatCurrency(row.value)}</td>
                        <td className="px-4 py-3 tabular-nums text-slate-700">{deltaLabel(row.change)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

export function AccountValueLegend({ dataset }: { dataset: AccountValueDataset }) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
      {dataset.accounts.map((account, index) => (
        <div key={account.accountId} className="flex items-center gap-2 text-sm font-medium text-slate-700">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: colorFor(index) }} />
          {account.accountName}
        </div>
      ))}
    </div>
  );
}

export function CurrentSnapshotPanel({
  dataset,
}: {
  dataset: AccountValueDataset;
}) {
  return (
    <div className="rounded-[28px] bg-white/88 p-5 shadow-[0_18px_50px_rgba(30,70,110,0.08)] ring-1 ring-slate-200/80">
      <div className="mb-4 flex items-center gap-2">
        <Landmark size={17} className="text-blue-600" />
        <div>
          <h3 className="text-lg font-black text-slate-950">Current Snapshot</h3>
          <p className="text-xs text-slate-500">Latest available account values</p>
        </div>
      </div>
      <div className="overflow-x-auto rounded-2xl border border-slate-200/80">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Account</th>
              <th className="px-4 py-3">Current Balance</th>
              <th className="px-4 py-3">Change</th>
              <th className="px-4 py-3">Trend</th>
            </tr>
          </thead>
          <tbody>
            {dataset.accounts.map((account, index) => (
              <tr key={account.accountId} className="border-t border-slate-200/70">
                <td className="px-4 py-3 font-bold text-slate-900">{account.accountName}</td>
                <td className="px-4 py-3 font-bold tabular-nums text-slate-950">
                  {account.latest ? formatCurrency(account.latest.value) : "-"}
                </td>
                <td className="px-4 py-3 font-semibold tabular-nums" style={{ color: (account.change ?? 0) >= 0 ? "#149a6a" : "#d84b36" }}>
                  {deltaLabel(account.change)} {account.changePct !== null ? `(${percentLabel(account.changePct)})` : ""}
                </td>
                <td className="w-32 px-4 py-3">
                  <Sparkline points={account.points} color={colorFor(index)} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export { colorFor };
