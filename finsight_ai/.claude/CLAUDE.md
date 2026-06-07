# Our Frame — Claude Code Project Guide

## What this project is
Our Frame is a privacy-first, multi-workspace family media platform.

Core goals:
- Each user keeps their original photos and videos in their own Google Drive.
- The app stores only the minimum metadata, access-control state, encrypted tokens, and personalization settings needed to run the product.
- The experience should feel premium, personal, and safe.
- Onboarding, Google login, Drive connection, and workspace setup must be smooth and deterministic.
- The codebase should support both a personal/family use case and a generic productized use case.

## Product principles
1. Privacy first
   - Never assume media should be copied into our database.
   - Prefer user-owned storage and least-privilege access.
   - Sensitive tokens must be encrypted at rest.
   - Minimize retained data.

2. Delightful onboarding
   - Onboarding should feel polished, emotional, and clear.
   - Every onboarding field should either:
     - drive UI personalization,
     - configure workspace behavior,
     - or be removed.

3. One source of truth
   - Workspace settings should drive:
     - app name,
     - theme,
     - layout preset,
     - onboarding completion status,
     - Drive root selection,
     - folder mapping strategy.

4. Low-lag media experience
   - Fast initial render.
   - Strong thumbnail/poster strategy.
   - Avoid unnecessary refetching.
   - Avoid giant payloads.
   - Use async I/O where it improves responsiveness.

5. Generic but opinionated
   - Make the platform configurable for each user/workspace.
   - Keep strong internal standards rather than allowing chaos.

## Architecture preferences
### Frontend
- Prefer Next.js + TypeScript for the long-term product direction.
- If the current codebase is React/Vite, changes should still be designed to migrate cleanly.
- Use a consistent design system with semantic tokens.
- Keep pages accessible, responsive, and emotionally polished.

### Backend
- Use FastAPI with clear router/service/repository separation.
- Use Pydantic v2 models for request/response contracts and internal typed schemas.
- Use asyncio for I/O-bound flows:
  - Google Drive calls
  - concurrent thumbnail/poster generation
  - metadata fetches
  - sync workflows
- Keep route handlers thin.
- Put orchestration logic in services.

### Data
- Production should use PostgreSQL.
- SQLite is acceptable only for local development.
- Store:
  - users
  - workspaces
  - workspace settings
  - access/invites
  - encrypted drive connections
  - sync state
  - derived metadata
- Do not store original media binaries.

### AI
Add AI only when it clearly improves the product.
Good uses:
- smart search
- semantic album descriptions
- caption suggestions
- memory/story generation
- duplicate or near-duplicate clustering
- photo quality surfacing
- scene/person/object search

Do not add AI just because it is cool.

### Vector DB guidance
Use a vector DB only when we need semantic retrieval over:
- captions
- OCR
- embeddings of photos/videos
- memories/stories
- cross-album semantic search

Do NOT add a vector DB in early phases just to say we have one.
Prefer staged rollout:
1. metadata + structured filters
2. generated captions/tags
3. embeddings + semantic search
4. hybrid search

## Security rules
- Never commit secrets.
- Never store Drive tokens unencrypted.
- Default to least privilege.
- Admin surfaces must be clearly separated from public product surfaces.
- Invite-only or explicit-access models are preferred over broad open sharing.
- Log security-relevant actions:
  - login
  - logout
  - invite creation
  - access grant/revoke
  - Drive connect/disconnect
  - workspace ownership changes

## Performance rules
- Always think in terms of:
  - above-the-fold load
  - cached thumbnails/posters
  - async concurrency
  - query count
  - payload size
  - image/video prefetch strategy
- Prefer measured improvements over guesses.

## UX rules
- Make state transitions obvious.
- Avoid redirect loops.
- Avoid dead-end onboarding steps.
- Profile, settings, and workspace controls should feel intentional and on-brand.
- Empty states should be helpful and beautiful.

## Coding standards
- Small, typed functions.
- Explicit naming.
- Centralized constants for route paths, status enums, theme keys, and config values.
- Add comments only when they explain intent, constraints, or non-obvious behavior.
- Prefer clear service methods over sprawling route logic.
- Write tests for:
  - auth/session edge cases
  - onboarding completion logic
  - workspace routing
  - Drive connect callbacks
  - sync edge cases
  - media URL/thumbnail logic

## When working in this repo
- First understand current behavior.
- Then identify the real source of truth.
- Then propose a minimal safe change.
- Then implement with clean wiring.
- Then validate the happy path and the obvious edge cases.
