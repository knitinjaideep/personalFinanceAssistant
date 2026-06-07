---
name: drive-map
description: Inspects Google Drive integration, folder assumptions, root selection, and mapping logic for albums, photos, and videos.
argument-hint: [optional-root-folder-or-scope]
disable-model-invocation: true
context: fork
agent: drive-structure-agent
---

Analyze the Drive structure and mapping behavior for:

$ARGUMENTS

If no argument is provided, inspect the current Drive integration end to end.

Tasks:
1. Find how folders are listed and selected.
2. Identify current hardcoded assumptions.
3. Design a root-folder selection model.
4. Design a dynamic folder-mapping strategy.
5. Support top 3 recommendations plus custom mapping.
6. Keep the model generic for multiple users/workspaces.

Return:
- current behavior
- risky assumptions
- proposed data model
- API changes
- frontend changes
- exact implementation plan
