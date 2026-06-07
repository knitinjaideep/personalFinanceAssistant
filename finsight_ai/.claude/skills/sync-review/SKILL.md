---
name: sync-review
description: Reviews Google Drive sync behavior, startup reconciliation, stale folder cleanup, and consistency between Drive and app state.
argument-hint: [optional-sync-scope]
disable-model-invocation: true
context: fork
agent: drive-structure-agent
---

Review the sync and reconciliation behavior for:

$ARGUMENTS

Inspect:
- backend startup sync logic
- how folder/file changes in Drive are detected
- how stale app data is cleaned up
- how favorites/slideshows/album covers stay consistent
- where manual refresh or cache invalidation may be needed

Return:
- current sync model
- failure modes
- consistency gaps
- recommended reconciliation strategy
- exact implementation plan
