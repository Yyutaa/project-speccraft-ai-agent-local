---
name: repo-coding-shared-module
description: Discover and apply shared-package usage, ownership, and cross-app impact rules in this repository.
---

# Repo Coding Shared Module

## Purpose

Confirm whether a real frontend shared package exists before proposing shared-module changes.

## Context Reading

- Read `AGENTS.md` for Repo Guide entry information.
- Read relevant `repo-profile.md` sections for stable facts, modification boundary, commands, shared package scope, app runtime topology, and app-to-package dependency mapping.
- Inspect current repository source files only when evidence is needed.

## Observed Evidence Entry Points

- No evidence found in lightweight sampling
- `packages/contracts`, `packages/agent-kernel`, and `packages/speccraft` are Python backend packages; `apps/web` has no JavaScript shared package and no `packages/*` import.
- These sampled paths are evidence entry points only. They are not global mandatory implementation rules. Prefer same app, same framework, and same module examples over these anchors when they differ.
- Treat these as lookup anchors, not mandatory global rules, unless the user explicitly confirms them as stable repository-level constraints.

## Framework-Specific Lookup

- React: No frontend shared package; inspect imports in `apps/web/src` to confirm there is no cross-package dependency.
- Vue: No evidence found in lightweight sampling
- H5: No evidence found in lightweight sampling

## What To Inspect

- Imports in `apps/web/src/App.tsx` and governance components
- `apps/web/package.json` dependencies

## What To Avoid

- Treating Python backend packages as frontend shared modules
- Creating a new shared package without confirmation
- Changing backend contract code from a frontend-scoped task

## Requires Confirmation

- Whether a frontend shared package is actually intended
- Whether the change belongs to the Python backend scope instead

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
- There is no frontend shared-package layer today; do not invent one.
