---
name: recommend-structure
description: Recommends the best Google Drive folder structures for a user's photo and video library, with presets and a custom option.
argument-hint: [describe-current-structure]
disable-model-invocation: true
context: fork
agent: drive-structure-agent
---

Recommend the best folder structure for the following user/workspace context:

$ARGUMENTS

If no structure is supplied, infer from the current codebase and product goals.

Output:
1. **Preset 1** — simple family-friendly
2. **Preset 2** — photographer-friendly
3. **Preset 3** — hybrid personal + pro
4. **Custom mapping model**
5. **Best default recommendation**
6. **How onboarding should present these choices**
7. **How to persist the chosen structure**
