---
name: e2e-happy-path
description: Validates the main user journey from login through onboarding, Drive connect, workspace setup, and home/gallery access.
argument-hint: [optional-flow]
disable-model-invocation: true
context: fork
agent: qa-flow-agent
---

Validate the main user journey for:

$ARGUMENTS

Cover at minimum:
- first login
- onboarding start
- onboarding resume
- Drive connect
- root folder selection
- personalization reflection
- landing in the correct page
- refresh behavior
- logout and return login

Return:
- happy path
- edge cases
- likely regressions
- recommended tests
- any fixes needed
