---
name: fix-auth-flow
description: Debugs and fixes login, session, onboarding, and post-OAuth redirect loops in this app.
argument-hint: [optional-route-or-bug-description]
disable-model-invocation: true
context: fork
agent: workspace-architecture-agent
---

Debug and fix the auth/setup routing problem described here:

$ARGUMENTS

If no argument is provided, inspect the current login + onboarding + workspace flow.

You must:
1. Trace unauthenticated -> authenticated -> workspace -> onboarding -> home transitions.
2. Identify the exact state source used at each branch.
3. Find duplicated or conflicting redirect logic.
4. Propose a canonical resolver.
5. Implement the safest minimal change.
6. Validate the happy path and page refresh behavior.

Deliver:
- concise root cause
- state machine
- files changed
- what was fixed
- follow-up tests or manual validation steps
