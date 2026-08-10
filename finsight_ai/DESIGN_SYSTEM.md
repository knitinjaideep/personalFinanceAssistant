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
