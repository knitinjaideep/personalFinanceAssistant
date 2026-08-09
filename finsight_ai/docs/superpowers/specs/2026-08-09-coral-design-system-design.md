# Coral Design System — Visual/Layout Foundation

Date: 2026-08-09
Status: Approved, ready for implementation planning
Companion docs: [CURRENT_ARCHITECTURE.md](../../../CURRENT_ARCHITECTURE.md), [REDESIGN_GAP_ANALYSIS.md](../../../REDESIGN_GAP_ANALYSIS.md), mockups in `docs/design/coral-{overview,banking,investments}-redesign.png`

## Goal

Establish a reusable, calmer, premium visual/layout system for Coral — "Apple-level restraint + Linear-style information hierarchy + modern fintech dashboard + subtle Coral underwater identity" — that the actual Overview/Banking/Investments redesign (a separate, future PR) will build on top of.

## Explicit non-goals for this PR

- No rebuild of Overview/Banking/Investments *content* — no new data fetching, no new charts, no PLAN vs ACTUAL logic, no Needs/Wants classification. That is all separately scoped in REDESIGN_GAP_ANALYSIS.md and out of scope here.
- No backend changes of any kind.
- No chatbot changes of any kind.
- No new navigation model — same 5 tabs (Overview/Banking/Investments/Documents/Chat) + Upload, just visually refined.
- No new npm dependencies (Framer Motion and Recharts are already installed and sufficient).

## Decisions made during brainstorming (see conversation for rationale)

1. **Page wrapper scope:** this PR *does* swap the outer wrapper of `app/page.tsx`, `app/banking/page.tsx`, `app/investments/page.tsx` onto the new `PageShell` — but touches nothing inside `HomePageClient`/`BankingPageClient`/`InvestmentsPageClient`. This is what makes the new system visible in the running app without rebuilding page content.
2. **Background:** edge-masked photo (radial mask fading the underwater photo out of the center, leaving a calm readable zone), not just a heavier gradient wash.
3. **Demo route:** a plain Next.js route (`app/design-system/page.tsx`), not linked from `TopNav`, ships in production but undiscoverable without the URL.

## 1. Token architecture

`app/globals.css` remains the source of truth (per CURRENT_ARCHITECTURE.md §1, `tailwind.config.ts`'s palette is largely dead at runtime — don't extend the dead system further). Add a new semantic token block to the existing `:root`/`[data-theme="dark"]`/`[data-theme="light"]` structure, then bridge into `tailwind.config.ts` `theme.extend.colors` as `var(--token)` references so new components can use utility classes (`bg-status-good`, `text-financial-needs`) instead of inline `style={{ color: 'var(...)' }}`.

New tokens (light / dark hex — to be verified for WCAG AA text contrast against `--bg-base` and `--card-bg` during implementation; adjust lightness if a pairing fails, keep the hue):

| Token | Light | Dark | Also add `-soft` bg tint |
|---|---|---|---|
| `--coral-primary` | `#FF7A5A` (existing) | `#FF7A5A` | yes |
| `--coral-primary-hover` | `#E8694B` (existing) | `#E8694B` | — |
| `--financial-needs` | `#2F6FE0` | `#5B9CFF` | yes |
| `--financial-wants` | `#E8593F` | `#FF8266` | yes |
| `--financial-savings` | `#2E9E76` | `#4FC79A` | yes |
| `--financial-investments` | `#7A6AE0` | `#9C8DFF` | yes |
| `--status-good` | `#2D8A70` | `#4CAF93` | yes |
| `--status-warning` | `#8A6A00` | `#C89A00` | yes |
| `--status-danger` | `#C43F3F` | `#E45757` | yes |
| `--status-neutral` | `#5B7284` | `#8AA5B8` | yes |

Rule enforced going forward: no new component may hardcode a hex/rgba color inline; it must reference one of these tokens (existing tokens like `--text-primary`/`--border-subtle` are also fine to keep using).

## 2. Background — `UnderwaterBackground.tsx`

Add a radial `mask-image`/`-webkit-mask-image` layer: transparent (photo hidden) across the center ~55–65% of the viewport, opaque (photo visible) toward the edges, feathered transition. Increase the existing gradient-wash overlay's opacity in the center so the readable zone sits on a near-solid `--bg-base` fill. Keep `BubbleField`/`ShimmerLayer` but reduce default intensity props so they don't compete with foreground content. No component API changes — internal implementation only, same props.

## 3. Navbar — `TopNav.tsx`

- Keep structure: `Brand`, 5 `NavLink`s, `UploadButton`, `ThemeToggle`, mobile drawer.
- Change: nav container's idle-state background goes from ~30%-opaque (`--nav-bg-idle`) to a lighter but consistently visible translucent surface at rest — adjust `--nav-bg-idle`/`--nav-bg-scrolled` tokens for both themes so the nav reads as "lightly translucent" immediately, not only after scroll/hover.
- Confirm `position: fixed` + `top-0` behaves as sticky once non-chat pages get a real internal scroll container from `PageShell` (today Home/Banking/Investments already use `overflow-y-auto` inner divs under a `fixed` nav, so this should already work — verify visually, don't restructure unless broken).
- Active tab keeps `--coral-primary` gradient pill (`--accent-coral-grad`) — already correct, no change needed there.

## 4. New components — `frontend-next/components/coral-ds/`

New folder, kept separate from `components/coral/` (the existing, still-used-elsewhere primitives) so the new system is unambiguous. Each is presentational-only: no data fetching, no business logic.

- **`PageShell.tsx`** — `{ children, width?: "default" | "wide" | "narrow" }`. Renders the nav-offset margin + `overflow-y-auto` scroll container + top mask-fade + max-width wrapper (default 1440px / wide 1680px / narrow 1040px) that today is copy-pasted across `app/page.tsx`, `app/banking/page.tsx`, `app/investments/page.tsx`. Absorbs and replaces `components/layout/PageContainer.tsx` (currently unused dead code per CURRENT_ARCHITECTURE.md §1) rather than adding a third overlapping wrapper.
- **`PageHeader.tsx`** — `{ eyebrow?, title, subtitle?, action? }`. Replaces hand-rolled header markup at the top of each `*PageClient`. Not wired into the `*PageClient`s in this PR (that's page-content territory) — available for the demo route and for the future content-redesign PR.
- **`GlobalPeriodFilter.tsx`** — `{ month: string, onMonthChange, range: "1M"|"3M"|"6M"|"YTD", onRangeChange }`. Presentational month dropdown + pill group matching the mockups. No data wiring — a future PR connects it to a real backend period parameter (REDESIGN_GAP_ANALYSIS.md item "date-range picker + unified period parameter").
- **`SectionHeader.tsx`** — reworked version of `components/coral/SectionHeader.tsx`, same prop shape, but eyebrow color and other inline colors replaced with token references.
- **`Surface.tsx`** — `{ children, padding?, className? }`. Calm base panel: card background token, 1px subtle border, small shadow — the "fewer cards, less noise" alternative to `GlassCard`'s heavier glass variants. `GlassCard` is not deleted (still used by `MetricCard` and elsewhere).
- **`InsightCard.tsx`** — `{ icon, title, description, tone: "good"|"warning"|"danger"|"neutral", action? }`. Tone drives left accent + icon tint via `--status-*`/`--financial-*` tokens.
- **`StatusBadge.tsx`** — `{ status: "good"|"warning"|"danger"|"neutral", children }`. Typed replacement for the CSS-class-based `.status-badge-*` system in `globals.css` (that CSS stays for now since `DocumentStatusBadge` still uses it — not touched this PR).
- **`VarianceBadge.tsx`** — `{ value: number, format?: "currency"|"percent" }`. Auto-colors green/red via `--status-good`/`--status-danger` based on sign; caller controls whether positive-is-good or positive-is-bad via a `direction?: "positive-good"|"negative-good"` prop (defaults to `positive-good`).
- **`TargetProgressBar.tsx`** — `{ label, actual: number, target: number, colorToken: "needs"|"wants"|"savings"|"investments" }`. Animates fill width on mount via Framer Motion, respects `prefers-reduced-motion`.
- **`MetricComparison.tsx`** — `{ label, actual: string, target: string }`. Small side-by-side stat pair.
- **`CoralAdvisorCard.tsx`** — `{ headline, body, actions? }`, wraps existing `CoralMascot`/`CoralDropletImage` in the mockups' "You're slightly off plan this month" pattern.
- **`EmptyState.tsx` / `SkeletonState.tsx` / `ErrorState.tsx`** — reworked from `components/coral/{EmptyState,ErrorState,LoadingState}.tsx`, same prop shapes where reasonable, tokens instead of inline colors. `SkeletonState` generalizes the ad hoc `.skeleton` class currently duplicated inline in `MetricCard.tsx`.

None of `HomePageClient`, `BankingPageClient`, `InvestmentsPageClient`, or any `features/*` data-fetching code is modified.

## 5. Typography & responsive

Keep the existing `clamp()`-based `--font-*` scale in `globals.css` (already fluid, already avoids "tiny on 27-inch"). Add only what new components need: a progress-bar/badge label size if the existing `--font-size-label` doesn't fit. `PageShell`'s `width` variants (1040/1440/1680px) are the mechanism for "sensible max width, not full-bleed on 2560, not cramped on 1440."

## 6. Motion

Framer Motion only (already a dependency). New usage: `PageShell` mount fade/slide (replacing the dead `components/motion/{FadeIn,StaggerGroup,FloatingPage}.tsx`, which get deleted as part of this work since they have zero importers and are being superseded), `TargetProgressBar` fill animation, hover elevation on `Surface`/`InsightCard`. All motion respects the existing global `prefers-reduced-motion` handling in `globals.css` — verify new keyframes/transitions are covered by that block, extend it if not.

## 7. Demo route

`app/design-system/page.tsx` — renders every new `coral-ds` component with representative props, a light/dark toggle, at multiple viewport-relevant widths conceptually (actual responsive testing happens via browser resize, not simulated in-page). Not linked in `TopNav`. This is the "story/demo route" deliverable in lieu of introducing Storybook.

## 8. Documentation

`DESIGN_SYSTEM.md` at repo root: token table (from §1), component inventory with prop tables (from §4), usage guidance (when to use `Surface` vs `GlassCard`, when to use `PageShell` widths), link to the demo route.

## 9. Files touched (exhaustive)

**New:**
- `frontend-next/components/coral-ds/{PageShell,PageHeader,GlobalPeriodFilter,SectionHeader,Surface,InsightCard,StatusBadge,VarianceBadge,TargetProgressBar,MetricComparison,CoralAdvisorCard,EmptyState,SkeletonState,ErrorState}.tsx`
- `frontend-next/app/design-system/page.tsx`
- `DESIGN_SYSTEM.md`

**Modified:**
- `frontend-next/app/globals.css` (new token block)
- `frontend-next/tailwind.config.ts` (Tailwind color bridge to new tokens)
- `frontend-next/components/coral/UnderwaterBackground.tsx` (edge mask)
- `frontend-next/components/layout/TopNav.tsx` (idle-state translucency tokens)
- `frontend-next/app/page.tsx`, `frontend-next/app/banking/page.tsx`, `frontend-next/app/investments/page.tsx` (swap wrapper to `PageShell`)

**Deleted:**
- `frontend-next/components/layout/PageContainer.tsx` (superseded by `PageShell`, was already dead code)
- `frontend-next/components/motion/{FadeIn,StaggerGroup,FloatingPage}.tsx` (zero importers, superseded)

**Not touched:** anything under `backend/`, `frontend-next/components/{home,banking,investments}/*PageClient.tsx`, `frontend-next/features/*`, `frontend-next/components/chat/*`, `frontend-next/components/documents/*`, `frontend-next/components/upload/*`, `frontend-next/store/appStore.ts`.

## 10. Verification plan

- `npm run lint` (existing ESLint config)
- Add a `typecheck` script (`tsc --noEmit`) if one doesn't exist; run it
- Check whether a test runner is configured at all (none was found during research — `package.json` has no test script); if none exists, state that explicitly rather than fabricating a pass
- `npm run build` (production Next.js build)
- Manual browser check of the demo route and the three wrapper-swapped pages, light + dark, at ~1440/1920/2560 widths and one tablet width, with `prefers-reduced-motion` toggled on to confirm motion is suppressed
