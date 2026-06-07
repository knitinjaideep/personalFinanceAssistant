---
name: audit-onboarding
description: Audits login and onboarding flows, identifies unused selections, and maps each onboarding field to storage and runtime behavior.
argument-hint: [optional-path-or-feature]
disable-model-invocation: true
context: fork
agent: onboarding-ux-agent
---

Run a focused audit of the onboarding and login experience for:

$ARGUMENTS

If no arguments are given, audit the current repo's default onboarding flow.

Your job:
1. Find the current onboarding entry points.
2. Find what data is collected.
3. Find where the data is stored.
4. Find where the data is read back.
5. Identify every selection that is not actually reflected in the UI or behavior.
6. Identify confusing or duplicated steps.
7. Identify redirect, resume, skip, and completion issues.

Return:
- **Flow summary**
- **Stored selections**
- **Selections actually used**
- **Dead or misleading fields**
- **UX issues**
- **Implementation plan**
- **Exact files to update**
