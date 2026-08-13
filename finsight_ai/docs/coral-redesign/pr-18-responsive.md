# PR 18 — Large-Screen & Responsive Polish

Perform a dedicated responsive pass.

Target:
- 1366x768
- 1440x900
- 1512x982
- 1920x1080
- 2560x1440
- iPad landscape
- iPad portrait

Fix the historical issue where Coral appears too small on large displays.

Use:
- clamp()
- responsive gaps
- responsive card padding
- fluid typography
- sensible content max widths

Do not simply scale the entire UI.

Large screens should allow charts/flows/multi-column layouts to breathe.
Tablet should stack gracefully without horizontal scrolling.

Never allow:
- tiny body text on 27-inch screens
- huge empty whitespace
- overstretched tables
- absurdly wide cards

Document responsive rules in DESIGN_SYSTEM.md.
