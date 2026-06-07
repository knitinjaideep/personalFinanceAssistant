# Our Frame Claude Code Pack

This pack includes:

- `.claude/CLAUDE.md`
- 8 project subagents in `.claude/agents/`
- 12 project skills in `.claude/skills/`

## Why this structure
Current Claude Code supports:
- project memory via `.claude/CLAUDE.md`
- project subagents via `.claude/agents/`
- slash-command style skills via `.claude/skills/<name>/SKILL.md`

## Install
Copy the `.claude/` folder into the root of your repo.

## Recommended first-use commands
- `/workspace-trace`
- `/audit-onboarding`
- `/fix-auth-flow`
- `/theme-wire`
- `/drive-map`

## Notes
- Skills are written as manual slash commands with `disable-model-invocation: true`.
- Most skills run in a forked context through a matching subagent.
- You may want to tailor specific agent tool permissions after trying them in your repo.
