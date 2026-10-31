---
name: repo-coding-permission
description: Discover and apply permission-point, feature-flag, and access-control rules in this repository.
---

# Repo Coding Permission

## Purpose

Determine whether a frontend permission model exists and keep server-side enforcement authoritative.

## Context Reading

- Read `AGENTS.md` for Repo Guide entry information.
- Read relevant `repo-profile.md` sections for stable facts, modification boundary, commands, shared package scope, app runtime topology, and app-to-package dependency mapping.
- Inspect current repository source files only when evidence is needed.

## Observed Evidence Entry Points

- No evidence found in lightweight sampling
- No permission helper, feature flag, or guarded UI component was found. The backend's read-only repository permission is not a frontend access-control layer.
- These sampled paths are evidence entry points only. They are not global mandatory implementation rules. Prefer same app, same framework, and same module examples over these anchors when they differ.
- Treat these as lookup anchors, not mandatory global rules, unless the user explicitly confirms them as stable repository-level constraints.

## Framework-Specific Lookup

- React: No evidence; inspect `apps/web/src/api.ts` and the touched UI only if a guard is explicitly requested.
- Vue: No evidence found in lightweight sampling
- H5: No evidence found in lightweight sampling

## What To Inspect

- `Run.available_commands` as the existing server-driven action gate
- Any UI affordance that could be mistaken for authorization

## What To Avoid

- Implementing client-only authorization
- Treating hidden buttons as a security boundary

## Requires Confirmation

- The permission model and enforcement point
- Whether the backend already rejects the action

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
- Server-side checks are authoritative; the frontend may only reflect them.
