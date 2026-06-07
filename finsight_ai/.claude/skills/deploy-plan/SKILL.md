---
name: deploy-plan
description: Produces a secure deployment plan for this app, including frontend, backend, database, secrets, admin isolation, and hardening.
argument-hint: [cloud-or-scope]
disable-model-invocation: true
context: fork
agent: security-privacy-agent
---

Create a secure deployment plan for:

$ARGUMENTS

If no platform is supplied, prefer a privacy-first production design suitable for this codebase.

Include:
- hosting topology
- public vs admin separation
- database choice
- secrets handling
- token encryption strategy
- logging/monitoring
- staging vs production
- rollout order
- top risks and mitigations

Return:
- recommended architecture
- why it fits this app
- exact environment/config checklist
- phased implementation plan
