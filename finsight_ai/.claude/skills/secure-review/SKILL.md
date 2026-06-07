---
name: secure-review
description: Reviews auth, token storage, admin boundaries, invite flows, and privacy-sensitive code for security issues.
argument-hint: [optional-scope]
disable-model-invocation: true
context: fork
agent: security-privacy-agent
---

Run a focused security and privacy review for:

$ARGUMENTS

Inspect:
- auth/session logic
- OAuth callbacks
- cookie/session configuration
- stored tokens/secrets
- admin pages/routes
- invite/share/access-control logic
- logging of security-sensitive actions

Return:
- risk summary
- issues by severity
- recommended mitigations
- exact code/config updates
- any follow-up hardening work
