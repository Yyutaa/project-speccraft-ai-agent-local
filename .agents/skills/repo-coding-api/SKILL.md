---
name: repo-coding-api
description: Discover and apply API client, request wrapper, response handling, and typed contract rules in this repository.
---

# Repo Coding API

## Purpose

Keep frontend network access inside the existing request wrapper and preserve server-projected response semantics.

## Context Reading

- Read `AGENTS.md` for Repo Guide entry information.
- Read relevant `repo-profile.md` sections for stable facts, modification boundary, commands, shared package scope, app runtime topology, and app-to-package dependency mapping.
- Inspect current repository source files only when evidence is needed.

## Observed Evidence Entry Points

- React: `apps/web/src/api.ts`
- React: `apps/web/vite.config.ts`
- `api.ts` owns the `fetch` wrapper, typed request/response types, and `WorkflowSyncPendingError`; the Vite proxy forwards `/api` to the FastAPI target.
- These sampled paths are evidence entry points only. They are not global mandatory implementation rules. Prefer same app, same framework, and same module examples over these anchors when they differ.
- Treat these as lookup anchors, not mandatory global rules, unless the user explicitly confirms them as stable repository-level constraints.

## Framework-Specific Lookup

- React: Inspect `apps/web/src/api.ts` first; it is the only HTTP boundary.
- Vue: No evidence found in lightweight sampling
- H5: No evidence found in lightweight sampling

## What To Inspect

- `apps/web/src/api.ts` request wrapper and error parsing
- `apps/web/src/App.tsx` response-to-state projection
- `apps/web/vite.config.ts` proxy target

## What To Avoid

- Adding a second HTTP client or direct `fetch` outside `api.ts`
- Computing workflow state in the browser instead of reading the Run response
- Optimistically mutating Run state after a write

## Requires Confirmation

- A new API boundary or contract version
- Any change to the `workflow_sync_pending` / `committed=true` handling

## Validation Hints

- `npm --prefix apps/web run typecheck`
- `npm --prefix apps/web run test`

## Response Guidance

Use natural language text. Lightweight section labels are optional and may include:

- Summary
- Evidence
- Confidence
- Warnings
- Stop Reasons
- Requires Confirmation
- Update Suggestions

## Guardrails

- Do not write runtime scan results into `AGENTS.md` or `repo-profile.md`.
- Prefer current source evidence over stale assumptions.
- Mark uncertain ownership, cross-team scope, or low-confidence inference under `Requires Confirmation`.
- Keep raw source data unchanged unless the user explicitly requests implementation changes.
- Preserve the `committed=true` recovery behavior: reread the Run, never resend the command.
- Do not move backend contract logic into the frontend.
