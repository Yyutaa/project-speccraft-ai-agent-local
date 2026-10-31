---
name: repo-coding-components
description: Discover and apply app-level component ownership, wrapper, and reuse rules in this repository.
---

# Repo Coding Components

## Purpose

Keep component ownership inside the single React app and reuse the existing Ant Design-based component patterns.

## Context Reading

- Read `AGENTS.md` for Repo Guide entry information.
- Read relevant `repo-profile.md` sections for stable facts, modification boundary, commands, shared package scope, app runtime topology, and app-to-package dependency mapping.
- Inspect current repository source files only when evidence is needed.

## Observed Evidence Entry Points

- React: `apps/web/src/GovernanceCreate.tsx`
- React: `apps/web/src/GovernanceResolution.tsx`
- React: `apps/web/src/TdGovernance.tsx`
- These are flat app-level components next to `App.tsx`, built from Ant Design primitives and props.
- These sampled paths are evidence entry points only. They are not global mandatory implementation rules. Prefer same app, same framework, and same module examples over these anchors when they differ.
- Treat these as lookup anchors, not mandatory global rules, unless the user explicitly confirms them as stable repository-level constraints.

## Framework-Specific Lookup

- React: Inspect the governance components and their shared fields before extracting or moving a component.
- Vue: No evidence found in lightweight sampling
- H5: No evidence found in lightweight sampling

## What To Inspect

- Component boundaries and props in `GovernanceCreate.tsx`, `GovernanceResolution.tsx`, `TdGovernance.tsx`
- Ant Design imports in `App.tsx`
- Whether a wrapper already exists for the requested UI

## What To Avoid

- Creating a shared package for app-local components
- Duplicating an existing wrapper
- Replacing Ant Design primitives with custom UI

## Requires Confirmation

- Whether the component should move between app-local and shared layers
- Whether a similar wrapper already exists elsewhere

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
- Component ownership is app-local until a real second consumer proves otherwise.
