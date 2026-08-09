# Coral Design System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable Coral design-system foundation (semantic tokens, a lighter edge-masked background, a refined navbar, and a set of presentational layout/content primitives) and make it visible by swapping the outer wrapper of Overview/Banking/Investments onto it — without touching any page's inner content, data-fetching, or the backend.

**Architecture:** `frontend-next/app/globals.css` stays the single source of truth for design tokens (CSS custom properties, light/dark via `[data-theme]`); `tailwind.config.ts` gets a thin bridge so new components can use Tailwind utility classes (`bg-status-good-soft`) instead of inline `style={{ color: 'var(...)' }}`. New components live in a fresh `frontend-next/components/coral-ds/` folder, kept separate from the still-in-use `components/coral/` folder. Everything is presentational only (no data fetching).

**Tech Stack:** Next.js 14 App Router, React 18, TypeScript (strict), Tailwind CSS 3.4, Framer Motion 12 (already installed — no new dependencies), lucide-react icons, `clsx`.

## Global Constraints

- No new npm dependencies (spec: "no new libraries").
- No backend changes. No changes to chatbot behavior or `components/chat/*`.
- Do not modify `HomePageClient.tsx`, `BankingPageClient.tsx`, `InvestmentsPageClient.tsx`, or anything under `frontend-next/features/*` — only the outer wrapper (`app/page.tsx`, `app/banking/page.tsx`, `app/investments/page.tsx`) may change.
- No hardcoded hex/rgba colors in any new `coral-ds` component — reference CSS custom property tokens only (new semantic tokens from Task 1, or existing tokens already in `globals.css`).
- No test runner is configured in this repo (`frontend-next/package.json` has no test script, no Jest/Vitest/RTL installed, and adding one is a new dependency, which is out of scope). Verification per task is therefore: TypeScript compiles clean (`tsc --noEmit`), ESLint passes (`npm run lint`), and — for anything visual — a real browser check via the Playwright MCP browser tools against the Next dev server (`npm run dev`, port 3001). This replaces the "write a failing test" step in tasks below.
- Respect `prefers-reduced-motion` (already globally handled in `globals.css`; any new Framer Motion usage must check `useReducedMotion()`).
- Dev server: `cd frontend-next && npm run dev` → `http://localhost:3001`. Start it once (Task 4) and leave it running; Next.js hot-reloads on file changes, so later tasks don't need to restart it, just re-navigate/refresh in the browser tool.

---

### Task 1: Semantic design tokens + Tailwind bridge

**Files:**
- Modify: `frontend-next/app/globals.css:181-183` (dark token block) and `frontend-next/app/globals.css:309-311` (light token block)
- Modify: `frontend-next/tailwind.config.ts:12-50` (colors object)

**Interfaces:**
- Produces: CSS custom properties `--coral-primary`, `--coral-primary-hover`, `--coral-primary-soft`, `--financial-needs(-soft)`, `--financial-wants(-soft)`, `--financial-savings(-soft)`, `--financial-investments(-soft)`, `--status-good(-soft)`, `--status-warning(-soft)`, `--status-danger(-soft)`, `--status-neutral(-soft)` (light + dark values). Tailwind color utilities of the same names (e.g. `bg-status-good-soft`, `text-financial-needs`).

- [ ] **Step 1: Add the dark-theme token values**

In `frontend-next/app/globals.css`, find this exact block (end of the `:root, [data-theme="dark"]` rule):

```css
  --success-text:      #4CAF93;
  --warning-strong:    #c89a00;
}
```

Replace with:

```css
  --success-text:      #4CAF93;
  --warning-strong:    #c89a00;

  /* ── Semantic design-system tokens (dark) ─────────────────────────── */
  --coral-primary:              #FF7A5A;
  --coral-primary-hover:        #E8694B;
  --coral-primary-soft:         rgba(255,122,90,0.14);

  --financial-needs:            #5B9CFF;
  --financial-needs-soft:       rgba(91,156,255,0.14);
  --financial-wants:            #FF8266;
  --financial-wants-soft:       rgba(255,130,102,0.14);
  --financial-savings:          #4FC79A;
  --financial-savings-soft:     rgba(79,199,154,0.14);
  --financial-investments:      #9C8DFF;
  --financial-investments-soft: rgba(156,141,255,0.14);

  --status-good:                #4CAF93;
  --status-good-soft:           rgba(76,175,147,0.14);
  --status-warning:             #C89A00;
  --status-warning-soft:        rgba(200,154,0,0.14);
  --status-danger:               #E45757;
  --status-danger-soft:         rgba(228,87,87,0.14);
  --status-neutral:             #8AA5B8;
  --status-neutral-soft:        rgba(138,165,184,0.14);
}
```

- [ ] **Step 2: Add the light-theme token values**

Find this exact block (end of the `[data-theme="light"]` rule):

```css
  --success-text:      #2D8A70;
  --warning-strong:    #8A6A00;
}
```

Replace with:

```css
  --success-text:      #2D8A70;
  --warning-strong:    #8A6A00;

  /* ── Semantic design-system tokens (light) ────────────────────────── */
  --coral-primary:              #FF7A5A;
  --coral-primary-hover:        #E8694B;
  --coral-primary-soft:         rgba(255,122,90,0.10);

  --financial-needs:            #2F6FE0;
  --financial-needs-soft:       rgba(47,111,224,0.10);
  --financial-wants:            #E8593F;
  --financial-wants-soft:       rgba(232,89,63,0.10);
  --financial-savings:          #2E9E76;
  --financial-savings-soft:     rgba(46,158,118,0.10);
  --financial-investments:      #7A6AE0;
  --financial-investments-soft: rgba(122,106,224,0.10);

  --status-good:                #2D8A70;
  --status-good-soft:           rgba(45,138,112,0.10);
  --status-warning:             #8A6A00;
  --status-warning-soft:        rgba(138,106,0,0.10);
  --status-danger:               #C43F3F;
  --status-danger-soft:         rgba(196,63,63,0.10);
  --status-neutral:             #5B7284;
  --status-neutral-soft:        rgba(91,114,132,0.10);
}
```

- [ ] **Step 3: Bridge the tokens into Tailwind**

In `frontend-next/tailwind.config.ts`, find the `colors: {` object (starts at line 12) and add a new key after the existing `highlight: "#FFD166",` line (line 49), still inside `colors: { ... }`:

```ts
        highlight: "#FFD166",

        "coral-primary": "var(--coral-primary)",
        "coral-primary-hover": "var(--coral-primary-hover)",
        "coral-primary-soft": "var(--coral-primary-soft)",

        "financial-needs": "var(--financial-needs)",
        "financial-needs-soft": "var(--financial-needs-soft)",
        "financial-wants": "var(--financial-wants)",
        "financial-wants-soft": "var(--financial-wants-soft)",
        "financial-savings": "var(--financial-savings)",
        "financial-savings-soft": "var(--financial-savings-soft)",
        "financial-investments": "var(--financial-investments)",
        "financial-investments-soft": "var(--financial-investments-soft)",

        "status-good": "var(--status-good)",
        "status-good-soft": "var(--status-good-soft)",
        "status-warning": "var(--status-warning)",
        "status-warning-soft": "var(--status-warning-soft)",
        "status-danger": "var(--status-danger)",
        "status-danger-soft": "var(--status-danger-soft)",
        "status-neutral": "var(--status-neutral)",
        "status-neutral-soft": "var(--status-neutral-soft)",
```

- [ ] **Step 4: Verify**

Run: `cd frontend-next && npx tsc --noEmit`
Expected: no new errors (CSS/Tailwind config changes don't affect `tsc`, this just confirms the baseline is still clean).

Run: `cd frontend-next && npm run lint`
Expected: no new errors.

Run: `cd frontend-next && npm run build`
Expected: build succeeds — this compiles `tailwind.config.ts` and `globals.css` and will fail loudly on a syntax error in either.

- [ ] **Step 5: Commit**

```bash
git add frontend-next/app/globals.css frontend-next/tailwind.config.ts
git commit -m "Add semantic design tokens and Tailwind bridge for Coral design system"
```

---

### Task 2: `PageShell` layout primitive

**Files:**
- Create: `frontend-next/components/coral-ds/PageShell.tsx`

**Interfaces:**
- Produces: `PageShell` (default export), `PageShellWidth = "narrow" | "default" | "wide"` (named type export) from `components/coral-ds/PageShell.tsx`. Props: `{ children: ReactNode; width?: PageShellWidth; className?: string }`.

- [ ] **Step 1: Create the component**

```tsx
import { clsx } from "clsx";
import type { ReactNode } from "react";

export type PageShellWidth = "narrow" | "default" | "wide";

interface PageShellProps {
  children: ReactNode;
  width?: PageShellWidth;
  className?: string;
}

const MAX_WIDTH: Record<PageShellWidth, string> = {
  narrow: "1040px",
  default: "1440px",
  wide: "1680px",
};

/**
 * Standard page wrapper: nav-offset margin, internal scroll container with a
 * top mask-fade, and a centered max-width column. Replaces the ~25-line
 * wrapper previously duplicated in app/page.tsx, app/banking/page.tsx, and
 * app/investments/page.tsx.
 */
export default function PageShell({ children, width = "default", className }: PageShellProps) {
  return (
    <div
      className="flex flex-col"
      style={{ marginTop: "var(--nav-height)", height: "calc(100dvh - var(--nav-height))" }}
    >
      <div
        className="flex-1 min-h-0 overflow-y-auto"
        style={{
          maskImage: "linear-gradient(to bottom, transparent 0px, black 32px)",
          WebkitMaskImage: "linear-gradient(to bottom, transparent 0px, black 32px)",
        }}
      >
        <div
          className={clsx("mx-auto w-full pb-12", className)}
          style={{
            maxWidth: MAX_WIDTH[width],
            paddingLeft: "var(--page-x-padding)",
            paddingRight: "var(--page-x-padding)",
            paddingTop: "1.5rem",
          }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify**

Run: `cd frontend-next && npx tsc --noEmit`
Expected: no errors.

Run: `cd frontend-next && npm run lint`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend-next/components/coral-ds/PageShell.tsx
git commit -m "Add PageShell layout primitive"
```

---

### Task 3: `PageHeader` + `GlobalPeriodFilter`

**Files:**
- Create: `frontend-next/components/coral-ds/PageHeader.tsx`
- Create: `frontend-next/components/coral-ds/GlobalPeriodFilter.tsx`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `PageHeader` (default export) from `components/coral-ds/PageHeader.tsx`, props `{ eyebrow?: string; title: string; subtitle?: string; action?: ReactNode; className?: string }`. `GlobalPeriodFilter` (default export), `PeriodRange = "1M" | "3M" | "6M" | "YTD"` (named type export) from `components/coral-ds/GlobalPeriodFilter.tsx`, props `{ month: string; onMonthClick?: () => void; range: PeriodRange; onRangeChange: (range: PeriodRange) => void; className?: string }`.

- [ ] **Step 1: Create `PageHeader`**

```tsx
import type { ReactNode } from "react";
import { clsx } from "clsx";

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  action?: ReactNode;
  className?: string;
}

export default function PageHeader({ eyebrow, title, subtitle, action, className }: PageHeaderProps) {
  return (
    <div className={clsx("flex items-start justify-between gap-6 flex-wrap mb-8", className)}>
      <div>
        {eyebrow && (
          <p className="eyebrow-text mb-2" style={{ color: "var(--coral-primary)" }}>
            {eyebrow}
          </p>
        )}
        <h1 className="page-title">{title}</h1>
        {subtitle && (
          <p className="body-text max-w-2xl mt-2" style={{ color: "var(--text-secondary)" }}>
            {subtitle}
          </p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
```

- [ ] **Step 2: Create `GlobalPeriodFilter`**

```tsx
import { clsx } from "clsx";
import { Calendar, ChevronDown } from "lucide-react";

export type PeriodRange = "1M" | "3M" | "6M" | "YTD";

const RANGE_OPTIONS: PeriodRange[] = ["1M", "3M", "6M", "YTD"];

interface GlobalPeriodFilterProps {
  month: string;
  onMonthClick?: () => void;
  range: PeriodRange;
  onRangeChange: (range: PeriodRange) => void;
  className?: string;
}

/**
 * Presentational month + range picker matching the redesign mockups.
 * No data wiring — callers own state. A future PR connects this to a real
 * backend period parameter (see REDESIGN_GAP_ANALYSIS.md).
 */
export default function GlobalPeriodFilter({
  month,
  onMonthClick,
  range,
  onRangeChange,
  className,
}: GlobalPeriodFilterProps) {
  return (
    <div className={clsx("flex items-center gap-2 flex-wrap", className)}>
      <button
        type="button"
        onClick={onMonthClick}
        className="inline-flex items-center gap-2 rounded-full px-3.5 py-2 coral-nav-text font-semibold"
        style={{ background: "var(--card-bg)", border: "1px solid var(--border-subtle)", color: "var(--text-secondary)" }}
      >
        <Calendar size={15} />
        {month}
        <ChevronDown size={14} />
      </button>

      <div
        className="inline-flex items-center rounded-full p-1 gap-0.5"
        style={{ background: "var(--card-bg)", border: "1px solid var(--border-subtle)" }}
        role="group"
        aria-label="Date range"
      >
        {RANGE_OPTIONS.map((option) => {
          const active = option === range;
          return (
            <button
              key={option}
              type="button"
              onClick={() => onRangeChange(option)}
              aria-pressed={active}
              className="rounded-full px-3 py-1.5 coral-nav-text font-semibold transition-colors"
              style={{
                background: active ? "var(--coral-primary)" : "transparent",
                color: active ? "var(--text-on-accent)" : "var(--text-secondary)",
              }}
            >
              {option}
            </button>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify**

Run: `cd frontend-next && npx tsc --noEmit && npm run lint`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend-next/components/coral-ds/PageHeader.tsx frontend-next/components/coral-ds/GlobalPeriodFilter.tsx
git commit -m "Add PageHeader and GlobalPeriodFilter components"
```

---

### Task 4: Design-system demo route skeleton

**Files:**
- Create: `frontend-next/app/design-system/page.tsx`

**Interfaces:**
- Consumes: `PageShell` (Task 2), `PageHeader`, `GlobalPeriodFilter`, `PeriodRange` (Task 3).
- Produces: route `http://localhost:3001/design-system`. Not linked from `TopNav` — reachable only by URL.

- [ ] **Step 1: Create the demo route**

```tsx
"use client";

import { useState } from "react";
import PageShell from "@/components/coral-ds/PageShell";
import PageHeader from "@/components/coral-ds/PageHeader";
import GlobalPeriodFilter, { type PeriodRange } from "@/components/coral-ds/GlobalPeriodFilter";

export default function DesignSystemPage() {
  const [month, setMonth] = useState("August 2026");
  const [range, setRange] = useState<PeriodRange>("1M");

  return (
    <PageShell width="wide">
      <PageHeader
        eyebrow="Design System"
        title="Coral Design System"
        subtitle="Reusable primitives for the redesigned dashboard — tokens, layout, and content components."
        action={
          <GlobalPeriodFilter
            month={month}
            onMonthClick={() => setMonth("August 2026")}
            range={range}
            onRangeChange={setRange}
          />
        }
      />

      <div className="space-y-12">{/* Later tasks append <section> blocks here */}</div>
    </PageShell>
  );
}
```

- [ ] **Step 2: Verify — start the dev server and check in a real browser**

Run in background: `cd frontend-next && npm run dev`
Wait for "Ready" in the log, then leave it running for the rest of this plan.

Using the Playwright browser tool: navigate to `http://localhost:3001/design-system`, take a screenshot, and check the browser console for errors.
Expected: page renders with the "Coral Design System" header, an "August 2026" pill, and the 1M/3M/6M/YTD range control (1M active); no console errors.

Click the "3M" pill via the browser tool and re-screenshot.
Expected: "3M" becomes visually active (coral background), "1M" returns to inactive.

- [ ] **Step 3: Commit**

```bash
git add frontend-next/app/design-system/page.tsx
git commit -m "Add design-system demo route skeleton"
```

---

### Task 5: `SectionHeader` (reworked)

**Files:**
- Create: `frontend-next/components/coral-ds/SectionHeader.tsx`

**Interfaces:**
- Produces: `SectionHeader` (default export) from `components/coral-ds/SectionHeader.tsx`. Same prop shape as the existing `components/coral/SectionHeader.tsx`: `{ eyebrow?: string; title: string; description?: string; action?: ReactNode; className?: string; size?: "sm" | "md" | "lg" }`.

- [ ] **Step 1: Create the component**

```tsx
import type { ReactNode } from "react";
import { clsx } from "clsx";

interface SectionHeaderProps {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
  size?: "sm" | "md" | "lg";
}

export default function SectionHeader({
  eyebrow,
  title,
  description,
  action,
  className,
  size = "md",
}: SectionHeaderProps) {
  const titleClass = size === "lg" ? "page-title" : size === "sm" ? "card-title-lg" : "section-title";
  const descClass = size === "lg" ? "body-text max-w-2xl" : size === "sm" ? "small-text" : "body-text max-w-xl";

  return (
    <div className={clsx("flex items-start justify-between gap-4 flex-wrap", className)}>
      <div>
        {eyebrow && (
          <p className="eyebrow-text mb-2" style={{ color: "var(--accent-strong)" }}>
            {eyebrow}
          </p>
        )}
        <h2 className={titleClass}>{title}</h2>
        {description && (
          <p className={clsx(descClass, "mt-2")} style={{ color: "var(--text-secondary)" }}>
            {description}
          </p>
        )}
      </div>
      {action && <div className="shrink-0 mt-1">{action}</div>}
    </div>
  );
}
```

- [ ] **Step 2: Add a demo section**

In `frontend-next/app/design-system/page.tsx`, add the import and replace the empty comment inside `<div className="space-y-12">`:

```tsx
import SectionHeader from "@/components/coral-ds/SectionHeader";
```

```tsx
      <div className="space-y-12">
        <section>
          <SectionHeader eyebrow="Foundations" title="Section header" description="Used above every content section." size="sm" />
        </section>
      </div>
```

- [ ] **Step 3: Verify**

Run: `cd frontend-next && npx tsc --noEmit && npm run lint`
Expected: no errors.

Using the Playwright browser tool: navigate (or refresh) `http://localhost:3001/design-system`, screenshot.
Expected: "Foundations / Section header" block renders below the page header.

- [ ] **Step 4: Commit**

```bash
git add frontend-next/components/coral-ds/SectionHeader.tsx frontend-next/app/design-system/page.tsx
git commit -m "Add SectionHeader component"
```

---

### Task 6: `Surface` primitive

**Files:**
- Create: `frontend-next/components/coral-ds/Surface.tsx`

**Interfaces:**
- Produces: `Surface` (default export) from `components/coral-ds/Surface.tsx`. Props: `{ children: ReactNode; padding?: "sm" | "md" | "lg"; className?: string; style?: CSSProperties; as?: "div" | "section" | "article" }`.

- [ ] **Step 1: Create the component**

```tsx
import { clsx } from "clsx";
import type { ReactNode, CSSProperties } from "react";

interface SurfaceProps {
  children: ReactNode;
  padding?: "sm" | "md" | "lg";
  className?: string;
  style?: CSSProperties;
  as?: "div" | "section" | "article";
}

const PADDING_CLASS: Record<NonNullable<SurfaceProps["padding"]>, string> = {
  sm: "p-4",
  md: "p-6",
  lg: "p-8",
};

/**
 * Calm base panel — the "fewer cards, less noise" alternative to GlassCard's
 * heavier glass variants. GlassCard is not replaced; it's still used by
 * MetricCard and other existing components.
 */
export default function Surface({ children, padding = "md", className, style, as: Tag = "div" }: SurfaceProps) {
  return (
    <Tag
      className={clsx("rounded-2xl", PADDING_CLASS[padding], className)}
      style={{
        background: "var(--card-bg)",
        border: "1px solid var(--border-subtle)",
        boxShadow: "var(--panel-shadow)",
        ...style,
      }}
    >
      {children}
    </Tag>
  );
}
```

- [ ] **Step 2: Add a demo section**

In `frontend-next/app/design-system/page.tsx`, add:

```tsx
import Surface from "@/components/coral-ds/Surface";
```

```tsx
        <section>
          <SectionHeader title="Surface" size="sm" />
          <Surface className="mt-4 max-w-md">
            <p className="small-text" style={{ color: "var(--text-secondary)" }}>
              A calm base panel used by InsightCard, CoralAdvisorCard, and other content components.
            </p>
          </Surface>
        </section>
```

- [ ] **Step 3: Verify**

Run: `cd frontend-next && npx tsc --noEmit && npm run lint`

Using the Playwright browser tool: refresh `http://localhost:3001/design-system`, screenshot.
Expected: a rounded panel with a subtle border/shadow renders under "Surface".

- [ ] **Step 4: Commit**

```bash
git add frontend-next/components/coral-ds/Surface.tsx frontend-next/app/design-system/page.tsx
git commit -m "Add Surface layout primitive"
```

---

### Task 7: `StatusBadge`

**Files:**
- Create: `frontend-next/components/coral-ds/StatusBadge.tsx`

**Interfaces:**
- Produces: `StatusBadge` (default export), `StatusTone = "good" | "warning" | "danger" | "neutral"` (named type export) from `components/coral-ds/StatusBadge.tsx`. Props: `{ status: StatusTone; children: ReactNode; className?: string }`.

- [ ] **Step 1: Create the component**

```tsx
import { clsx } from "clsx";
import type { ReactNode } from "react";

export type StatusTone = "good" | "warning" | "danger" | "neutral";

interface StatusBadgeProps {
  status: StatusTone;
  children: ReactNode;
  className?: string;
}

const TONE_CLASS: Record<StatusTone, string> = {
  good: "bg-status-good-soft text-status-good",
  warning: "bg-status-warning-soft text-status-warning",
  danger: "bg-status-danger-soft text-status-danger",
  neutral: "bg-status-neutral-soft text-status-neutral",
};

export default function StatusBadge({ status, children, className }: StatusBadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-1 coral-badge-text font-semibold",
        TONE_CLASS[status],
        className
      )}
    >
      {children}
    </span>
  );
}
```

- [ ] **Step 2: Add a demo section**

In `frontend-next/app/design-system/page.tsx`, add:

```tsx
import StatusBadge from "@/components/coral-ds/StatusBadge";
```

```tsx
        <section>
          <SectionHeader title="Badges" size="sm" />
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <StatusBadge status="good">On track</StatusBadge>
            <StatusBadge status="warning">Slightly behind</StatusBadge>
            <StatusBadge status="danger">Off plan</StatusBadge>
            <StatusBadge status="neutral">No data</StatusBadge>
          </div>
        </section>
```

- [ ] **Step 3: Verify**

Run: `cd frontend-next && npx tsc --noEmit && npm run lint`

Using the Playwright browser tool: refresh `http://localhost:3001/design-system`, screenshot in both light and dark theme (use the nav's theme toggle).
Expected: 4 pill badges, each with a distinct soft-background/text color pairing that stays legible in both themes.

- [ ] **Step 4: Commit**

```bash
git add frontend-next/components/coral-ds/StatusBadge.tsx frontend-next/app/design-system/page.tsx
git commit -m "Add StatusBadge component"
```

---

### Task 8: `VarianceBadge`

**Files:**
- Create: `frontend-next/components/coral-ds/VarianceBadge.tsx`

**Interfaces:**
- Consumes: `StatusBadge`, `StatusTone` (Task 7).
- Produces: `VarianceBadge` (default export) from `components/coral-ds/VarianceBadge.tsx`. Props: `{ value: number; format?: "currency" | "percent"; direction?: "positive-good" | "negative-good"; className?: string }`.

- [ ] **Step 1: Create the component**

```tsx
import { clsx } from "clsx";
import StatusBadge, { type StatusTone } from "./StatusBadge";

interface VarianceBadgeProps {
  value: number;
  format?: "currency" | "percent";
  direction?: "positive-good" | "negative-good";
  className?: string;
}

function formatValue(value: number, format: "currency" | "percent"): string {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  const abs = Math.abs(value);
  const body = format === "currency" ? `$${abs.toLocaleString()}` : `${abs}%`;
  return `${sign}${body}`;
}

function toneFor(value: number, direction: "positive-good" | "negative-good"): StatusTone {
  if (value === 0) return "neutral";
  const isPositive = value > 0;
  const isGood = direction === "positive-good" ? isPositive : !isPositive;
  return isGood ? "good" : "danger";
}

/** Delta badge (e.g. "+$80" / "-$45") that auto-colors via StatusBadge based on sign and direction. */
export default function VarianceBadge({ value, format = "currency", direction = "positive-good", className }: VarianceBadgeProps) {
  return (
    <StatusBadge status={toneFor(value, direction)} className={clsx("tabular-nums", className)}>
      {formatValue(value, format)}
    </StatusBadge>
  );
}
```

- [ ] **Step 2: Add to the demo section**

In `frontend-next/app/design-system/page.tsx`, add the import and extend the badges section:

```tsx
import VarianceBadge from "@/components/coral-ds/VarianceBadge";
```

```tsx
            <StatusBadge status="neutral">No data</StatusBadge>
            <VarianceBadge value={80} />
            <VarianceBadge value={-45} />
            <VarianceBadge value={12} format="percent" direction="negative-good" />
```

- [ ] **Step 3: Verify**

Run: `cd frontend-next && npx tsc --noEmit && npm run lint`

Using the Playwright browser tool: refresh, screenshot.
Expected: "+$80" green, "-$45" red, "+12%" red (since `direction="negative-good"` flips the polarity).

- [ ] **Step 4: Commit**

```bash
git add frontend-next/components/coral-ds/VarianceBadge.tsx frontend-next/app/design-system/page.tsx
git commit -m "Add VarianceBadge component"
```

---

### Task 9: `TargetProgressBar`

**Files:**
- Create: `frontend-next/components/coral-ds/TargetProgressBar.tsx`

**Interfaces:**
- Produces: `TargetProgressBar` (default export), `FinancialBucket = "needs" | "wants" | "savings" | "investments"` (named type export) from `components/coral-ds/TargetProgressBar.tsx`. Props: `{ label: string; actual: number; target: number; bucket: FinancialBucket; className?: string }`.

- [ ] **Step 1: Create the component**

```tsx
"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { CSSProperties } from "react";

export type FinancialBucket = "needs" | "wants" | "savings" | "investments";

interface TargetProgressBarProps {
  label: string;
  actual: number;
  target: number;
  bucket: FinancialBucket;
  className?: string;
}

const BUCKET_VAR: Record<FinancialBucket, string> = {
  needs: "var(--financial-needs)",
  wants: "var(--financial-wants)",
  savings: "var(--financial-savings)",
  investments: "var(--financial-investments)",
};

/** Labeled progress bar (actual % vs target %), colored by bucket. Includes a screen-reader-only textual summary. */
export default function TargetProgressBar({ label, actual, target, bucket, className }: TargetProgressBarProps) {
  const prefersReducedMotion = useReducedMotion();
  const color = BUCKET_VAR[bucket];
  const clampedActual = Math.max(0, Math.min(actual, 100));
  const targetPosition = Math.max(0, Math.min(target, 100));

  const trackStyle: CSSProperties = { background: "var(--border-subtle)" };

  return (
    <div className={className}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="coral-card-title">{label}</span>
        <span className="small-text" style={{ color: "var(--text-muted)" }}>
          Target {target}%
        </span>
      </div>
      <div className="relative h-2 rounded-full overflow-hidden" style={trackStyle}>
        <motion.div
          className="h-full rounded-full"
          style={{ background: color }}
          initial={{ width: prefersReducedMotion ? `${clampedActual}%` : 0 }}
          animate={{ width: `${clampedActual}%` }}
          transition={{ duration: prefersReducedMotion ? 0 : 0.6, ease: [0.22, 1, 0.36, 1] }}
        />
        <div
          className="absolute top-0 bottom-0 w-px"
          style={{ left: `${targetPosition}%`, background: "var(--text-dim)" }}
          aria-hidden
        />
      </div>
      <span className="sr-only">
        {label}: {actual}% actual against a {target}% target.
      </span>
    </div>
  );
}
```

- [ ] **Step 2: Add a demo section**

In `frontend-next/app/design-system/page.tsx`, add:

```tsx
import TargetProgressBar from "@/components/coral-ds/TargetProgressBar";
```

```tsx
        <section>
          <SectionHeader title="Target progress" size="sm" />
          <Surface className="mt-4 grid gap-5 max-w-xl">
            <TargetProgressBar label="Needs" actual={48} target={50} bucket="needs" />
            <TargetProgressBar label="Wants" actual={24} target={20} bucket="wants" />
            <TargetProgressBar label="Savings" actual={12} target={15} bucket="savings" />
            <TargetProgressBar label="Investments" actual={16} target={15} bucket="investments" />
          </Surface>
        </section>
```

- [ ] **Step 3: Verify**

Run: `cd frontend-next && npx tsc --noEmit && npm run lint`

Using the Playwright browser tool: refresh, screenshot; confirm 4 bars each fill to roughly the right proportion with distinct bucket colors and a thin target-line marker.

Using the OS/browser "reduce motion" emulation (or Playwright's `browser_navigate` after setting `prefers-reduced-motion: reduce` via `browser_evaluate`/device emulation if available; otherwise inspect the code path), confirm bars render at final width immediately with no animation when reduced motion is active — this is enforced by the `prefersReducedMotion` check in the component, so it's acceptable to verify by code review if the tool can't emulate the media query.

- [ ] **Step 4: Commit**

```bash
git add frontend-next/components/coral-ds/TargetProgressBar.tsx frontend-next/app/design-system/page.tsx
git commit -m "Add TargetProgressBar component"
```

---

### Task 10: `MetricComparison`

**Files:**
- Create: `frontend-next/components/coral-ds/MetricComparison.tsx`

**Interfaces:**
- Produces: `MetricComparison` (default export) from `components/coral-ds/MetricComparison.tsx`. Props: `{ label: string; actual: string; target: string; className?: string }`.

- [ ] **Step 1: Create the component**

```tsx
interface MetricComparisonProps {
  label: string;
  actual: string;
  target: string;
  className?: string;
}

export default function MetricComparison({ label, actual, target, className }: MetricComparisonProps) {
  return (
    <div className={className}>
      <p className="eyebrow-text mb-1">{label}</p>
      <div className="flex items-baseline gap-2">
        <span className="metric-value-sm tabular-nums" style={{ color: "var(--text-strong)" }}>
          {actual}
        </span>
        <span className="small-text tabular-nums" style={{ color: "var(--text-muted)" }}>
          / {target} target
        </span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add a demo section**

In `frontend-next/app/design-system/page.tsx`, add:

```tsx
import MetricComparison from "@/components/coral-ds/MetricComparison";
```

```tsx
        <section>
          <SectionHeader title="Metric comparison" size="sm" />
          <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricComparison label="401(k)" actual="5.8%" target="6%" />
            <MetricComparison label="Roth IRA" actual="2.1%" target="4%" />
          </div>
        </section>
```

- [ ] **Step 3: Verify**

Run: `cd frontend-next && npx tsc --noEmit && npm run lint`

Using the Playwright browser tool: refresh, screenshot.
Expected: two label/value pairs render side by side.

- [ ] **Step 4: Commit**

```bash
git add frontend-next/components/coral-ds/MetricComparison.tsx frontend-next/app/design-system/page.tsx
git commit -m "Add MetricComparison component"
```

---

### Task 11: `InsightCard`

**Files:**
- Create: `frontend-next/components/coral-ds/InsightCard.tsx`

**Interfaces:**
- Consumes: `Surface` (Task 6), `StatusTone` (Task 7).
- Produces: `InsightCard` (default export) from `components/coral-ds/InsightCard.tsx`. Props: `{ icon: ReactNode; title: string; description: string; tone: StatusTone; action?: ReactNode; className?: string }`.

- [ ] **Step 1: Create the component**

```tsx
import type { ReactNode } from "react";
import { clsx } from "clsx";
import Surface from "./Surface";
import type { StatusTone } from "./StatusBadge";

interface InsightCardProps {
  icon: ReactNode;
  title: string;
  description: string;
  tone: StatusTone;
  action?: ReactNode;
  className?: string;
}

const TONE_ICON_CLASS: Record<StatusTone, string> = {
  good: "bg-status-good-soft text-status-good",
  warning: "bg-status-warning-soft text-status-warning",
  danger: "bg-status-danger-soft text-status-danger",
  neutral: "bg-status-neutral-soft text-status-neutral",
};

/** Icon + title + description insight card, e.g. "Overspending in Wants". */
export default function InsightCard({ icon, title, description, tone, action, className }: InsightCardProps) {
  return (
    <Surface padding="md" className={clsx("flex flex-col gap-3", className)}>
      <span className={clsx("w-9 h-9 rounded-xl flex items-center justify-center shrink-0", TONE_ICON_CLASS[tone])}>
        {icon}
      </span>
      <div>
        <h4 className="coral-card-title mb-1">{title}</h4>
        <p className="small-text" style={{ color: "var(--text-secondary)" }}>{description}</p>
      </div>
      {action && <div className="mt-1">{action}</div>}
    </Surface>
  );
}
```

- [ ] **Step 2: Add a demo section**

In `frontend-next/app/design-system/page.tsx`, add:

```tsx
import InsightCard from "@/components/coral-ds/InsightCard";
import { ShoppingBag, PiggyBank, TrendingUp } from "lucide-react";
```

```tsx
        <section>
          <SectionHeader title="Insight cards" size="sm" />
          <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
            <InsightCard icon={<ShoppingBag size={17} />} tone="danger" title="Overspending in Wants" description="You're over your Wants target by $80 this month." />
            <InsightCard icon={<PiggyBank size={17} />} tone="warning" title="Under-saving for House Fund" description="You're $45 behind your monthly savings goal." />
            <InsightCard icon={<TrendingUp size={17} />} tone="good" title="On track for 401(k)" description="Great job! You're meeting your retirement contributions." />
          </div>
        </section>
```

- [ ] **Step 3: Verify**

Run: `cd frontend-next && npx tsc --noEmit && npm run lint`

Using the Playwright browser tool: refresh, screenshot.
Expected: 3 cards render with distinct tone-colored icon chips (red/amber/green).

- [ ] **Step 4: Commit**

```bash
git add frontend-next/components/coral-ds/InsightCard.tsx frontend-next/app/design-system/page.tsx
git commit -m "Add InsightCard component"
```

---

### Task 12: `CoralAdvisorCard`

**Files:**
- Create: `frontend-next/components/coral-ds/CoralAdvisorCard.tsx`

**Interfaces:**
- Consumes: `Surface` (Task 6), `CoralMascot` (existing, `components/coral/CoralMascot.tsx`, default export, props include `variant?: CoralMascotVariant`, `size?: CoralMascotSize`).
- Produces: `CoralAdvisorCard` (default export) from `components/coral-ds/CoralAdvisorCard.tsx`. Props: `{ headline: string; body: string; actions?: ReactNode; className?: string }`.

- [ ] **Step 1: Create the component**

```tsx
import type { ReactNode } from "react";
import Surface from "./Surface";
import CoralMascot from "@/components/coral/CoralMascot";

interface CoralAdvisorCardProps {
  headline: string;
  body: string;
  actions?: ReactNode;
  className?: string;
}

/** Mascot + headline insight pattern from the top of each mockup page (e.g. "You're slightly off plan this month"). */
export default function CoralAdvisorCard({ headline, body, actions, className }: CoralAdvisorCardProps) {
  return (
    <Surface padding="md" className={className}>
      <div className="flex items-start gap-4">
        <CoralMascot size="sm" animated={false} />
        <div className="flex-1 min-w-0">
          <h3 className="coral-card-title mb-1.5">{headline}</h3>
          <p className="small-text" style={{ color: "var(--text-secondary)" }}>{body}</p>
          {actions && <div className="mt-3 flex flex-col gap-2">{actions}</div>}
        </div>
      </div>
    </Surface>
  );
}
```

- [ ] **Step 2: Add a demo section**

In `frontend-next/app/design-system/page.tsx`, add:

```tsx
import CoralAdvisorCard from "@/components/coral-ds/CoralAdvisorCard";
```

```tsx
        <section>
          <SectionHeader title="Coral advisor" size="sm" />
          <CoralAdvisorCard
            className="mt-4 max-w-xl"
            headline="You're slightly off plan this month"
            body="Spending in Wants is running above plan, and you're saving a bit less than your target."
          />
        </section>
```

- [ ] **Step 3: Verify**

Run: `cd frontend-next && npx tsc --noEmit && npm run lint`

Using the Playwright browser tool: refresh, screenshot.
Expected: mascot bubble renders next to the headline/body text inside a `Surface` panel.

- [ ] **Step 4: Commit**

```bash
git add frontend-next/components/coral-ds/CoralAdvisorCard.tsx frontend-next/app/design-system/page.tsx
git commit -m "Add CoralAdvisorCard component"
```

---

### Task 13: `EmptyState`, `ErrorState`, `SkeletonState`

**Files:**
- Create: `frontend-next/components/coral-ds/EmptyState.tsx`
- Create: `frontend-next/components/coral-ds/ErrorState.tsx`
- Create: `frontend-next/components/coral-ds/SkeletonState.tsx`

**Interfaces:**
- Produces: `EmptyState` (default export, `{ icon?: ReactNode; title: string; description?: string; action?: ReactNode; compact?: boolean }`), `ErrorState` (default export, `{ title?: string; message?: string; onRetry?: () => void; compact?: boolean }`), `SkeletonState` (default export, `{ variant?: "text" | "block" | "card"; width?: string; height?: string; className?: string; count?: number }`) from their respective files in `components/coral-ds/`.

- [ ] **Step 1: Create `EmptyState`**

```tsx
import type { ReactNode } from "react";
import { FileSearch } from "lucide-react";

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  compact?: boolean;
}

export default function EmptyState({ icon, title, description, action, compact = false }: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center text-center rounded-2xl ${compact ? "py-10 px-6" : "py-20 px-8"}`}
      style={{ background: "var(--status-neutral-soft)", border: "1px solid var(--status-neutral-soft)" }}
    >
      <div
        className="flex items-center justify-center rounded-2xl mb-5"
        style={{
          width: compact ? 48 : 64,
          height: compact ? 48 : 64,
          background: "var(--card-bg)",
          border: "1px solid var(--border-subtle)",
          color: "var(--status-neutral)",
        }}
      >
        {icon ?? <FileSearch size={compact ? 22 : 28} />}
      </div>

      <h3 className={compact ? "card-title-lg mb-2" : "section-title mb-3"}>{title}</h3>

      {description && (
        <p className={`${compact ? "small-text" : "body-text"} max-w-sm`} style={{ color: "var(--text-secondary)" }}>
          {description}
        </p>
      )}

      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
```

- [ ] **Step 2: Create `ErrorState`**

```tsx
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
```

- [ ] **Step 3: Create `SkeletonState`**

```tsx
import { clsx } from "clsx";

interface SkeletonStateProps {
  variant?: "text" | "block" | "card";
  width?: string;
  height?: string;
  className?: string;
  count?: number;
}

const SHAPE_CLASS: Record<NonNullable<SkeletonStateProps["variant"]>, string> = {
  text: "rounded-md",
  block: "rounded-lg",
  card: "rounded-2xl",
};

const DEFAULT_HEIGHT: Record<NonNullable<SkeletonStateProps["variant"]>, string> = {
  text: "0.9rem",
  block: "2.5rem",
  card: "8rem",
};

/** Generalizes the ad hoc `.skeleton` class usage (previously duplicated inline in MetricCard). */
export default function SkeletonState({ variant = "block", width, height, className, count = 1 }: SkeletonStateProps) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className={clsx("skeleton", SHAPE_CLASS[variant], className)}
          style={{ width: width ?? "100%", height: height ?? DEFAULT_HEIGHT[variant] }}
        />
      ))}
    </>
  );
}
```

- [ ] **Step 4: Add a demo section**

In `frontend-next/app/design-system/page.tsx`, add:

```tsx
import EmptyState from "@/components/coral-ds/EmptyState";
import ErrorState from "@/components/coral-ds/ErrorState";
import SkeletonState from "@/components/coral-ds/SkeletonState";
import { Landmark } from "lucide-react";
```

```tsx
        <section>
          <SectionHeader title="States" size="sm" />
          <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
            <EmptyState compact icon={<Landmark size={22} />} title="No accounts yet" description="Upload a statement to get started." />
            <ErrorState compact message="Could not load this section." onRetry={() => {}} />
            <Surface padding="sm" className="space-y-2">
              <SkeletonState variant="text" width="60%" />
              <SkeletonState variant="text" width="40%" />
              <SkeletonState variant="block" height="2rem" />
            </Surface>
          </div>
        </section>
```

- [ ] **Step 5: Verify**

Run: `cd frontend-next && npx tsc --noEmit && npm run lint`

Using the Playwright browser tool: refresh, screenshot.
Expected: empty state, error state (with a "Try again" button), and a shimmering skeleton block render side by side.

- [ ] **Step 6: Commit**

```bash
git add frontend-next/components/coral-ds/EmptyState.tsx frontend-next/components/coral-ds/ErrorState.tsx frontend-next/components/coral-ds/SkeletonState.tsx frontend-next/app/design-system/page.tsx
git commit -m "Add EmptyState, ErrorState, and SkeletonState components"
```

---

### Task 14: `UnderwaterBackground` edge mask

**Files:**
- Modify: `frontend-next/components/coral/UnderwaterBackground.tsx`

**Interfaces:**
- No prop or export changes — internal implementation only.

- [ ] **Step 1: Mask the photo to the edges**

In `frontend-next/components/coral/UnderwaterBackground.tsx`, find:

```tsx
      {/* Real photo background */}
      <Image
        key={imgSrc}
        src={imgSrc}
        alt=""
        fill
        priority
        className="object-cover object-center"
        style={{ transition: "opacity 0.5s ease" }}
        sizes="100vw"
      />
```

Replace with:

```tsx
      {/* Real photo background — masked to the edges so the center reading zone stays clean */}
      <Image
        key={imgSrc}
        src={imgSrc}
        alt=""
        fill
        priority
        className="object-cover object-center"
        style={{
          transition: "opacity 0.5s ease",
          maskImage: "radial-gradient(ellipse 68% 62% at 50% 38%, transparent 45%, black 100%)",
          WebkitMaskImage: "radial-gradient(ellipse 68% 62% at 50% 38%, transparent 45%, black 100%)",
        }}
        sizes="100vw"
      />
```

- [ ] **Step 2: Reduce ambient bubble/shimmer intensity so they don't compete with foreground content**

Find:

```tsx
      <ShimmerLayer
        intensity={isLight ? 0.42 : 0.55}
        color={isLight ? "rgba(95,168,211,0.22)" : "rgba(103,232,249,0.22)"}
      />
```

Replace with:

```tsx
      <ShimmerLayer
        intensity={isLight ? 0.28 : 0.36}
        color={isLight ? "rgba(95,168,211,0.22)" : "rgba(103,232,249,0.22)"}
      />
```

Find:

```tsx
      <BubbleField
        intensity={isLight ? 0.85 : 1}
        color={isLight ? "rgba(31,111,139,0.55)" : "rgba(103,232,249,0.65)"}
        fill={isLight ? "rgba(31,111,139,0.10)" : "rgba(34,211,238,0.12)"}
      />
```

Replace with:

```tsx
      <BubbleField
        intensity={isLight ? 0.55 : 0.65}
        color={isLight ? "rgba(31,111,139,0.55)" : "rgba(103,232,249,0.65)"}
        fill={isLight ? "rgba(31,111,139,0.10)" : "rgba(34,211,238,0.12)"}
      />
```

- [ ] **Step 3: Verify**

Run: `cd frontend-next && npx tsc --noEmit && npm run lint`

Using the Playwright browser tool: navigate to `http://localhost:3001/design-system`, screenshot in both light and dark theme.
Expected: the underwater photo is visible at the far edges/corners of the viewport and fades to the flat background color across the center ~55–65% where content sits; bubbles are present but subdued.

- [ ] **Step 4: Commit**

```bash
git add frontend-next/components/coral/UnderwaterBackground.tsx
git commit -m "Mask underwater background to page edges for a calmer content zone"
```

---

### Task 15: `TopNav` translucent-idle fix

**Files:**
- Modify: `frontend-next/app/globals.css` (nav idle tokens)
- Modify: `frontend-next/components/layout/TopNav.tsx`

**Interfaces:**
- No prop changes. Fixes a latent bug: `.nav-container` hover/focus CSS rules already exist in `globals.css` but the `nav-container` class was never applied to the actual `<motion.nav>` element, and its `style` prop hardcoded `background: "transparent"` — so the nav has had no visible idle background at all. This task makes the "lightly translucent" requirement real.

- [ ] **Step 1: Raise the idle background tokens so they read as "lightly translucent" rather than invisible**

In `frontend-next/app/globals.css`, in the dark `[data-theme="dark"]`/`:root` block, find:

```css
  --nav-bg-idle:       rgba(5,18,34,0.28);   /* transparent at rest */
```

Replace with:

```css
  --nav-bg-idle:       rgba(5,22,40,0.55);   /* lightly translucent at rest */
```

In the `[data-theme="light"]` block, find:

```css
  --nav-bg-idle:       rgba(255,255,255,0.38);
```

Replace with:

```css
  --nav-bg-idle:       rgba(255,255,255,0.62);
```

- [ ] **Step 2: Actually apply the idle background/border/blur to the nav, and attach the `nav-container` class so the existing hover CSS activates**

In `frontend-next/components/layout/TopNav.tsx`, find:

```tsx
          /*
           * group/nav — all children can react to nav-level hover via
           * group-hover/nav: variants without adding JS state.
           *
           * Idle:  ~30% opaque glass that blends into the underwater scene.
           * Hover: richer glass surface + lift + cyan glow ring.
           */
          className="
            group/nav
            pointer-events-auto mt-5
            flex items-center justify-between gap-3
            rounded-full
            px-3 sm:px-4 py-2
          "
          style={{ background: "transparent", border: "none", boxShadow: "none" }}
        >
```

Replace with:

```tsx
          /*
           * group/nav — all children can react to nav-level hover via
           * group-hover/nav: variants without adding JS state.
           * nav-container drives the idle → hover background/border/shadow
           * transition via CSS (see .nav-container rules in globals.css),
           * since Tailwind group-hover can't interpolate between two
           * dynamic CSS var() values.
           */
          className="
            group/nav nav-container
            pointer-events-auto mt-5
            flex items-center justify-between gap-3
            rounded-full
            px-3 sm:px-4 py-2
          "
          style={{
            background: "var(--nav-bg-idle)",
            border: "1px solid var(--nav-border-idle)",
            boxShadow: "var(--nav-shadow-idle)",
            backdropFilter: "blur(20px)",
            WebkitBackdropFilter: "blur(20px)",
          }}
        >
```

- [ ] **Step 3: Verify**

Run: `cd frontend-next && npx tsc --noEmit && npm run lint`

Using the Playwright browser tool: navigate to `http://localhost:3001/design-system`, screenshot in both light and dark theme, and hover the nav area.
Expected: the nav now shows a visible translucent glass surface at rest (not fully transparent) in both themes, and becomes richer/more opaque on hover (via the pre-existing `.nav-container:hover` CSS rule).

- [ ] **Step 4: Commit**

```bash
git add frontend-next/app/globals.css frontend-next/components/layout/TopNav.tsx
git commit -m "Fix navbar idle state to render a visible translucent surface"
```

---

### Task 16: Swap Overview/Banking/Investments page wrappers to `PageShell`

**Files:**
- Modify: `frontend-next/app/page.tsx`
- Modify: `frontend-next/app/banking/page.tsx`
- Modify: `frontend-next/app/investments/page.tsx`

**Interfaces:**
- Consumes: `PageShell` (Task 2). No changes to `HomePageClient`, `BankingPageClient`, or `InvestmentsPageClient` — only the wrapper around them.

- [ ] **Step 1: Rewrite `app/page.tsx`**

Replace the full file contents with:

```tsx
import HomePageClient from "@/components/home/HomePageClient";
import PageShell from "@/components/coral-ds/PageShell";

export default function HomePage() {
  return (
    <PageShell>
      <HomePageClient />
    </PageShell>
  );
}
```

- [ ] **Step 2: Rewrite `app/banking/page.tsx`**

Replace the full file contents with:

```tsx
import BankingPageClient from "@/components/banking/BankingPageClient";
import PageShell from "@/components/coral-ds/PageShell";

export default function BankingPage() {
  return (
    <PageShell>
      <BankingPageClient />
    </PageShell>
  );
}
```

- [ ] **Step 3: Rewrite `app/investments/page.tsx`**

Read the current file first to confirm the client component's import path (expected: `@/components/investments/InvestmentsPageClient`), then replace the full file contents with:

```tsx
import InvestmentsPageClient from "@/components/investments/InvestmentsPageClient";
import PageShell from "@/components/coral-ds/PageShell";

export default function InvestmentsPage() {
  return (
    <PageShell>
      <InvestmentsPageClient />
    </PageShell>
  );
}
```

- [ ] **Step 4: Verify**

Run: `cd frontend-next && npx tsc --noEmit && npm run lint`
Expected: no errors — `PageShell`'s output is structurally identical to the old inline wrapper, so this should be a clean drop-in.

Using the Playwright browser tool: navigate to `http://localhost:3001/`, `http://localhost:3001/banking`, and `http://localhost:3001/investments` in turn; screenshot each in light and dark theme.
Expected: all three pages render exactly as before (same content, same data), but now sit inside the new edge-masked background and translucent nav from Tasks 14–15. No layout shift, no missing content, no console errors.

- [ ] **Step 5: Commit**

```bash
git add frontend-next/app/page.tsx frontend-next/app/banking/page.tsx frontend-next/app/investments/page.tsx
git commit -m "Swap Overview/Banking/Investments outer wrapper to PageShell"
```

---

### Task 17: Delete superseded dead code

**Files:**
- Delete: `frontend-next/components/layout/PageContainer.tsx`
- Delete: `frontend-next/components/motion/FadeIn.tsx`
- Delete: `frontend-next/components/motion/StaggerGroup.tsx`
- Delete: `frontend-next/components/motion/FloatingPage.tsx`

**Interfaces:** none — this task only removes files confirmed to have zero importers.

- [ ] **Step 1: Confirm zero importers before deleting**

Run:
```bash
cd frontend-next
grep -rn "PageContainer" app components features --include="*.tsx" --include="*.ts"
grep -rn "components/motion/FadeIn\|components/motion/StaggerGroup\|components/motion/FloatingPage" app components features --include="*.tsx" --include="*.ts"
```
Expected: no matches outside the files themselves (CURRENT_ARCHITECTURE.md §14/REDESIGN_GAP_ANALYSIS.md already confirmed this, but re-verify since Task 16 just touched the pages that used to inline `PageContainer`'s equivalent markup). If any importer is found, stop and investigate before deleting — do not delete a file still in use.

- [ ] **Step 2: Delete the files**

```bash
git rm frontend-next/components/layout/PageContainer.tsx
git rm frontend-next/components/motion/FadeIn.tsx
git rm frontend-next/components/motion/StaggerGroup.tsx
git rm frontend-next/components/motion/FloatingPage.tsx
```

- [ ] **Step 3: Verify**

Run: `cd frontend-next && npx tsc --noEmit && npm run lint && npm run build`
Expected: all pass — a broken import would surface as a `tsc`/build failure.

- [ ] **Step 4: Commit**

```bash
git commit -m "Remove dead PageContainer and unused motion components superseded by PageShell"
```

---

### Task 18: `DESIGN_SYSTEM.md`

**Files:**
- Create: `DESIGN_SYSTEM.md` (repo root, alongside `CURRENT_ARCHITECTURE.md`)

**Interfaces:** documentation only.

- [ ] **Step 1: Write the document**

```markdown
# Coral Design System

Foundational visual/layout system for Coral's premium dashboard redesign. Established in the design-system PR (see `docs/superpowers/specs/2026-08-09-coral-design-system-design.md` for the full spec and rationale); the Overview/Banking/Investments *content* redesign is separate, future work (see `REDESIGN_GAP_ANALYSIS.md`).

Live component gallery: `/design-system` (not linked in the nav — visit the URL directly).

## Principles

Apple-level restraint + Linear-style information hierarchy + modern fintech dashboard + subtle Coral underwater identity. Fewer cards, more whitespace, a calm readable center zone, underwater artwork pushed to the page edges.

## Tokens

All tokens are CSS custom properties defined in `frontend-next/app/globals.css`, with light/dark values under `[data-theme="light"]`/`[data-theme="dark"]`, bridged into Tailwind (`tailwind.config.ts`) as utility classes. **Never hardcode a hex/rgba color in a new component** — reference a token.

| Token | Purpose | Tailwind utility |
|---|---|---|
| `--coral-primary` / `--coral-primary-hover` | Brand accent (buttons, active nav, links) | `bg-coral-primary`, `text-coral-primary` |
| `--financial-needs` | "Needs" bucket accent | `bg-financial-needs`, `text-financial-needs` |
| `--financial-wants` | "Wants" bucket accent | `bg-financial-wants`, `text-financial-wants` |
| `--financial-savings` | "Savings" bucket accent | `bg-financial-savings`, `text-financial-savings` |
| `--financial-investments` | "Investments" bucket accent | `bg-financial-investments`, `text-financial-investments` |
| `--status-good` | Positive/on-track state | `bg-status-good`, `text-status-good` |
| `--status-warning` | Caution/slightly-off state | `bg-status-warning`, `text-status-warning` |
| `--status-danger` | Negative/off-plan state | `bg-status-danger`, `text-status-danger` |
| `--status-neutral` | No-data/informational state | `bg-status-neutral`, `text-status-neutral` |

Each also has a `-soft` variant (e.g. `--status-good-soft`) — a low-alpha tint for badge/card backgrounds, used instead of Tailwind's opacity modifiers (which don't work on `var()`-indirected colors).

## Layout primitives

- **`PageShell`** (`components/coral-ds/PageShell.tsx`) — standard page wrapper: nav-offset margin, scroll container, max-width column. `width="narrow" | "default" | "wide"` (1040 / 1440 / 1680px). Use this instead of hand-rolling a page wrapper.
- **`PageHeader`** — eyebrow + title + subtitle + right-aligned action slot (typically a `GlobalPeriodFilter`).
- **`GlobalPeriodFilter`** — month + 1M/3M/6M/YTD range control. Presentational only — no data wiring yet.
- **`SectionHeader`** — heading used above a content section, three sizes.
- **`Surface`** — calm base panel (card background, subtle border, small shadow). Prefer this over `GlassCard`'s heavier glass variants for new dashboard content.

## Content primitives

- **`InsightCard`** — icon + title + description + tone (`good`/`warning`/`danger`/`neutral`), e.g. "Overspending in Wants."
- **`CoralAdvisorCard`** — mascot + headline + body, e.g. "You're slightly off plan this month."
- **`StatusBadge`** — tone-colored pill.
- **`VarianceBadge`** — auto-colored delta (e.g. "+$80"/"-$45"), sign-aware via a `direction` prop.
- **`TargetProgressBar`** — actual vs target progress bar, colored by financial bucket, animates on mount (respects reduced motion), includes a screen-reader text alternative.
- **`MetricComparison`** — small actual/target label pair.
- **`EmptyState` / `ErrorState` / `SkeletonState`** — standard state components for loading/empty/error UI.

## What's not new

`GlassCard`, `MetricCard`, `CoralMascot`/`CoralDropletImage`, `UnderwaterBackground`, `TopNav`/`AppShell`, and the existing `components/coral/*` primitives are unchanged (aside from the background edge-mask and navbar idle-state fix) and remain in use elsewhere in the app.

## Adding a new component

1. Put it in `frontend-next/components/coral-ds/`.
2. Use only design tokens (above) for color — no hardcoded hex/rgba.
3. If it renders a chart or progress indicator, include a text alternative (see `TargetProgressBar`'s `sr-only` summary for the pattern).
4. Wrap any new Framer Motion animation with a `useReducedMotion()` check.
5. Add a demo section to `/design-system` (`frontend-next/app/design-system/page.tsx`).
```

- [ ] **Step 2: Verify**

Confirm the file renders correctly as Markdown (no broken tables/code fences) by reading it back.

- [ ] **Step 3: Commit**

```bash
git add DESIGN_SYSTEM.md
git commit -m "Document the Coral design system"
```

---

### Task 19: Full verification pass

**Files:**
- Modify: `frontend-next/package.json` (add `typecheck` script)

**Interfaces:** none — this is a verification-only task, no new components.

- [ ] **Step 1: Add a `typecheck` script**

In `frontend-next/package.json`, find:

```json
    "lint": "eslint \"app/**/*.{ts,tsx}\" \"components/**/*.{ts,tsx}\" \"features/**/*.{ts,tsx}\" \"lib/**/*.{ts,tsx}\" \"store/**/*.{ts,tsx}\""
```

Replace with:

```json
    "lint": "eslint \"app/**/*.{ts,tsx}\" \"components/**/*.{ts,tsx}\" \"features/**/*.{ts,tsx}\" \"lib/**/*.{ts,tsx}\" \"store/**/*.{ts,tsx}\"",
    "typecheck": "tsc --noEmit"
```

- [ ] **Step 2: Run the automated gates**

```bash
cd frontend-next
npm run lint
npm run typecheck
npm run build
```
Expected: all three succeed with zero errors. If `npm run build` fails on something unrelated to this PR's changes (e.g. a pre-existing issue), note it explicitly rather than silently working around it — do not use `--no-verify`-style shortcuts.

- [ ] **Step 3: Confirm no test runner exists (don't fabricate a "tests pass" claim)**

```bash
grep -c '"test"' frontend-next/package.json || true
find frontend-next -maxdepth 2 -iname "*.test.*" -o -iname "*.spec.*" | grep -v node_modules || true
```
Expected: no test script, no test files. Record this fact plainly when reporting completion instead of claiming a test suite passed.

- [ ] **Step 4: Cross-page, cross-theme, cross-viewport visual QA via Playwright**

Using the Playwright browser tool, for each of `http://localhost:3001/`, `/banking`, `/investments`, `/documents`, `/chat`, `/design-system`:
- Resize to 1440×900, 1920×1080, 2560×1440, and a tablet size (e.g. 834×1194); screenshot each.
  Expected: content never becomes tiny/lost on 2560 (governed by `PageShell`'s max-width + the existing `clamp()` typography), and never feels cramped at 1440. No horizontal scrollbar at any width.
- Toggle light/dark via the nav's theme button at each page; screenshot both.
  Expected: nav is legibly translucent in both themes (Task 15), background photo only visible at the edges (Task 14), all new token-driven components (visited via `/design-system`) keep sufficient text contrast in both themes.
- Check the browser console on every navigation for errors/warnings introduced by this PR.
- Tab through the nav links and the `/design-system` page's interactive elements (range pills, retry button) using keyboard-only navigation (Playwright `browser_press_key` with `Tab`/`Enter`); confirm a visible focus ring appears (global `:focus-visible` rule in `globals.css`) and every control is reachable.

- [ ] **Step 5: Commit**

```bash
git add frontend-next/package.json
git commit -m "Add typecheck script and complete design-system verification pass"
```

---

## Self-review notes

- **Spec coverage:** Task 1 → tokens; Task 14 → background; Task 15 → navbar; Tasks 2–13 → all 14 components listed in the spec (`PageShell`, `PageHeader`, `GlobalPeriodFilter`, `SectionHeader`, `Surface`, `InsightCard`, `StatusBadge`, `VarianceBadge`, `TargetProgressBar`, `MetricComparison`, `CoralAdvisorCard`, `EmptyState`, `SkeletonState`, `ErrorState`); Task 16 → wrapper swap; Task 17 → dead-code deletion; Task 18 → `DESIGN_SYSTEM.md`; Task 4 → demo route; Task 19 → lint/typecheck/build + the "no test runner" honesty requirement from the spec's verification plan.
- **Type consistency checked:** `StatusTone` defined once in `StatusBadge.tsx` (Task 7) and imported by `VarianceBadge` (Task 8) and `InsightCard` (Task 11) rather than redeclared. `PeriodRange` defined once in `GlobalPeriodFilter.tsx` (Task 3) and imported by the demo route (Task 4). `FinancialBucket` defined once in `TargetProgressBar.tsx` (Task 9).
- **No placeholders:** every step has complete, real code; no "TBD"/"similar to Task N".
