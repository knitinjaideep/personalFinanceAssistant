# Coral Redesign Engineering Workflow

The redesign is implemented sequentially.

Do not run dependent implementation phases in parallel.

## Phase workflow

For each work item:

### 1. Read

Read:

- CLAUDE.md
- applicable `.claude/rules/`
- coral-redesign skill
- current STATE.md
- task specification
- relevant architecture docs
- relevant implementation

### 2. Inspect before changing

Determine:

- what already exists
- what can be reused
- what must be modified
- what would be duplication

### 3. Implement

Delegate implementation to `coral-implementer`.

The implementer must not commit.

### 4. Review

Delegate to `coral-reviewer`.

The reviewer must independently inspect:

- work-order requirements
- git diff
- related implementation
- financial invariants
- architecture
- tests

Reviewer may fix ordinary implementation issues.

Reviewer must escalate genuine product or architecture decisions.

### 5. Verify

Delegate to `coral-verifier`.

Verification should run the canonical verification command plus any phase-specific checks.

Verifier does not redesign or refactor.

### 6. Resolve failures

If verification fails:

- fix root cause
- do not disable tests
- re-run verification

### 7. Commit

Only after PASS:

- inspect git diff
- stage relevant files
- create one coherent commit
- update STATE.md with commit SHA

### 8. Continue

Proceed to next incomplete task or milestone.

## Stop conditions

Stop and request human input only when:

- requirements conflict
- a destructive migration is necessary
- a fundamental financial-policy decision is missing
- existing source data cannot support a required feature and multiple product interpretations are possible
- a security-sensitive action requires owner approval
- verification cannot safely be made to pass

Routine implementation decisions are not blockers.

## Forbidden autonomous actions

Do not:

- push main
- merge PRs
- deploy
- force push
- reset --hard
- disable branch protection
- modify external production infrastructure

## State recovery

STATE.md is authoritative for progress.

If a Claude session ends:

1. start a new session
2. read STATE.md
3. inspect repository status and git log
4. continue from first incomplete task