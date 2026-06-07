---
name: theme-wire
description: Verifies that onboarding-selected app name, theme, layout, and profile styling are actually reflected across the UI.
argument-hint: [optional-page-or-component]
disable-model-invocation: true
context: fork
agent: design-system-agent
---

Audit and wire theme/personalization for:

$ARGUMENTS

Tasks:
1. Find the selected branding/theme/layout fields.
2. Find where they are stored.
3. Find where the app shell reads them.
4. Identify missing runtime usage.
5. Update the UI so the choices are visible and coherent.
6. Make the top-right profile area clickable, themed, and polished.

Return:
- current personalization wiring
- gaps
- token/component changes
- exact files to edit
- implementation summary
