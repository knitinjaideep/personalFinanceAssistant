---
name: coral-redesign-run
description: Runs the Coral redesign sequentially from STATE.md using the implementer, reviewer, and verifier subagents.
disable-model-invocation: true
---

# Run Coral Redesign

You are the orchestration layer.

The user has explicitly invoked this workflow.

Read:

- `CLAUDE.md`
- `docs/coral-redesign/STATE.md`
- `docs/coral-redesign/MILESTONES.md`
- `.claude/skills/coral-redesign/SKILL.md`

Inspect git status before doing anything.

## Safety preflight

Confirm:

- current branch is not `main`
- repository does not contain unexpected uncommitted work unrelated to redesign
- required task files exist

If unrelated uncommitted work exists, stop and tell the user.

Do not discard it.

## Execution model

Work milestone by milestone.

Within a milestone, execute its task files in listed order.

For each task:

### Implement

Delegate the task to:

`coral-implementer`

Provide:

- exact work-order path
- current milestone
- relevant acceptance criteria

Wait for completion.

### Review

Delegate an independent review to:

`coral-reviewer`

Provide:

- work-order path
- milestone acceptance criteria

Reviewer must inspect git diff directly.

If reviewer returns BLOCKED:

stop the workflow.

If reviewer fixes issues:

continue.

### Verify

Delegate to:

`coral-verifier`.

Require:

- canonical verification command
- task-specific checks

If verification fails:

send the concrete failures to `coral-implementer` for repair.

Then rerun reviewer only if repair materially changes logic.

Rerun verifier.

Limit repeated repair loops.

If the same class of failure persists after reasonable attempts, mark BLOCKED and stop.

## Milestone completion

After every task in a milestone passes:

1. inspect git diff yourself
2. verify no unrelated changes
3. run canonical verification once more
4. stage milestone files
5. create one coherent milestone commit
6. update `STATE.md`
7. include commit SHA
8. continue

Suggested commit style:

- `feat(finance): add plan-vs-actual transaction intelligence`
- `feat(overview): redesign monthly financial overview`
- `feat(banking): add cash-flow and drift experience`
- `feat(investments): add contribution-plan experience`
- `feat(planning): add goals and monthly planning`
- `feat(ui): complete Coral financial redesign polish`
- `chore(audit): complete redesign verification`

Use the actual milestone scope.

## State

STATE.md is authoritative.

Never mark something complete before verification passes.

## Stop conditions

Stop for:

- missing product policy
- destructive migration
- financial ambiguity that cannot be safely inferred
- security-sensitive change
- unresolved repeated verification failure

Do not stop for:

- naming decisions
- ordinary refactors
- minor component decisions
- routine tests
- routine API shape choices consistent with repo

## Forbidden

Never:

- push
- merge
- deploy
- force push
- reset hard
- modify main
- remove existing user data

## Final completion

After the final audit passes:

1. update STATE.md to COMPLETE
2. show the user:
   - milestone commits
   - final verification status
   - known limitations
   - manual visual checks they should perform

Do not push.

Do not merge.