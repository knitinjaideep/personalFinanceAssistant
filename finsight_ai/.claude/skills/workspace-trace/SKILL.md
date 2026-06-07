---
name: workspace-trace
description: Traces active workspace selection, onboarding status, Drive status, and route decisions to explain why the app is landing on a specific screen.
argument-hint: [optional-user-flow]
disable-model-invocation: true
context: fork
agent: workspace-architecture-agent
---

Trace the current workspace routing behavior for:

$ARGUMENTS

You must inspect:
- current user fetch
- workspace list / active workspace logic
- onboarding completion checks
- Drive connection checks
- route guards and redirect effects

Return:
- actual state machine
- current decision points
- why the app lands where it does
- where duplication exists
- exact fixes to make route selection deterministic
