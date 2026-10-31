---
name: repo-coding-enum
description: Discover and apply enum-source, option-mapping, and status-display rules in this repository.
---

# Repo Coding Enum

## Purpose

Keep union types and display labels sourced from the existing shared definitions instead of duplicating literals.

## Context Reading

- Read `AGENTS.md` for Repo Guide entry information.
- Read relevant `repo-profile.md` sections for stable facts, modification boundary, commands, shared package scope, app runtime topology, and app-to-package dependency mapping.
- Inspect current repository source files only when evidence is needed.

## Observed Evidence Entry Points

- React: `apps/web/src/governance.ts`
- React: `apps/web/src/api.ts`
- `governance.ts` defines `dimensionLabels` and `dimensionOptions`; `api.ts` defines the shared union types.
- These sampled paths are evidence entry points only. They are not global mandatory implementation rules. Prefer same app, same framework, and same module examples over these anchors when they differ.
- Treat these as lookup anchors, not mandatory global rules, unless the user explicitly confirms them as stable repository-level constraints.

## Framework-Specific Lookup

- React: Inspect `apps/web/src/governance.ts` and the union types in `apps/web/src/api.ts`.
- Vue: No evidence found in lightweight sampling
- H5: No evidence found in lightweight sampling

## What To Inspect

- `dimensionLabels` / `dimensionOptions` in `governance.ts`
- Status and command unions in `api.ts`
- Existing label maps in `App.tsx`

## What To Avoid

- Duplicating label maps or status strings
- Defining a second enum source for the same domain concept

## Requires Confirmation

- A new shared enum source
- Whether a display label belongs to the domain or a single component

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
- Prefer the existing union type and label map over a new local enum.
