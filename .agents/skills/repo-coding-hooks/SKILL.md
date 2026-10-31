---
name: repo-coding-hooks
description: Discover and apply hook-organization, request-hook, and side-effect rules in this repository.
---

# Repo Coding Hooks

## Purpose

Determine whether a reusable hook exists or is warranted before extracting side-effect logic.

## Context Reading

- Read `AGENTS.md` for Repo Guide entry information.
- Read relevant `repo-profile.md` sections for stable facts, modification boundary, commands, shared package scope, app runtime topology, and app-to-package dependency mapping.
- Inspect current repository source files only when evidence is needed.

## Observed Evidence Entry Points

- No evidence found in lightweight sampling
- No custom hooks directory or `use*` helper was found; `App.tsx` uses inline `useEffect` / `useState`.
- These sampled paths are evidence entry points only. They are not global mandatory implementation rules. Prefer same app, same framework, and same module examples over these anchors when they differ.
- Treat these as lookup anchors, not mandatory global rules, unless the user explicitly confirms them as stable repository-level constraints.

## Framework-Specific Lookup

- React: No custom hook evidence; inspect inline effects in `apps/web/src/App.tsx` when a change touches them.
- Vue: No evidence found in lightweight sampling
- H5: No evidence found in lightweight sampling

## What To Inspect

- `useEffect` blocks in `App.tsx`
- Whether the same side effect is repeated across governance components

## What To Avoid

- Extracting a hook without a second real consumer
- Adding a state or data-fetching library to replace a small effect

## Requires Confirmation

- Whether a hook should be shared across components
- Whether the effect is workflow logic that belongs on the server

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
- Do not move server-authoritative workflow behavior into a client hook.
