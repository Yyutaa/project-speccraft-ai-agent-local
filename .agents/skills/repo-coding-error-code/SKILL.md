---
name: repo-coding-error-code
description: Discover and apply error-code parsing, message mapping, and compatibility rules in this repository.
---

# Repo Coding Error Code

## Purpose

Handle stable API error codes and workflow-specific failure semantics without inventing a parallel error taxonomy.

## Context Reading

- Read `AGENTS.md` for Repo Guide entry information.
- Read relevant `repo-profile.md` sections for stable facts, modification boundary, commands, shared package scope, app runtime topology, and app-to-package dependency mapping.
- Inspect current repository source files only when evidence is needed.

## Observed Evidence Entry Points

- React: `apps/web/src/api.ts`
- React: `apps/web/src/App.tsx`
- `api.ts` parses `detail.code` for `workflow_sync_pending`; `App.tsx` renders request errors and the committed-command warning.
- These sampled paths are evidence entry points only. They are not global mandatory implementation rules. Prefer same app, same framework, and same module examples over these anchors when they differ.
- Treat these as lookup anchors, not mandatory global rules, unless the user explicitly confirms them as stable repository-level constraints.

## Framework-Specific Lookup

- React: Inspect `apps/web/src/api.ts` error parsing and `apps/web/src/App.tsx` error rendering.
- Vue: No evidence found in lightweight sampling
- H5: No evidence found in lightweight sampling

## What To Inspect

- `detail.code` handling and status checks in `api.ts`
- User-visible error text and retained input in `App.tsx`

## What To Avoid

- String-matching error codes not defined by the shared contract
- Swallowing `503` workflow synchronization failures
- Inventing client-only error codes

## Requires Confirmation

- A new error-code family or backend contract change
- Whether an error should block or merely warn

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
- Error codes are contract facts; the frontend may map them to UI states but must not redefine their meaning.
