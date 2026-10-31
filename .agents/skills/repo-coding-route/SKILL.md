---
name: repo-coding-route
description: Discover and apply route registration, page entry, and route-parameter rules in this repository.
---

# Repo Coding Route

## Purpose

Locate the real page-entry and mounting surface before adding routes or route parameters.

## Context Reading

- Read `AGENTS.md` for Repo Guide entry information.
- Read relevant `repo-profile.md` sections for stable facts, modification boundary, commands, shared package scope, app runtime topology, and app-to-package dependency mapping.
- Inspect current repository source files only when evidence is needed.

## Observed Evidence Entry Points

- React: `apps/web/src/main.tsx`
- React: `apps/web/src/App.tsx`
- No router package or route table exists; `main.tsx` mounts `App` directly.
- These sampled paths are evidence entry points only. They are not global mandatory implementation rules. Prefer same app, same framework, and same module examples over these anchors when they differ.
- Treat these as lookup anchors, not mandatory global rules, unless the user explicitly confirms them as stable repository-level constraints.

## Framework-Specific Lookup

- React: `apps/web/src/main.tsx` mounts the single `App` entry; there is no route registry.
- Vue: No evidence found in lightweight sampling
- H5: No evidence found in lightweight sampling

## What To Inspect

- `apps/web/src/main.tsx` and `apps/web/src/App.tsx`
- `apps/web/vite.config.ts` if a path or proxy change is involved

## What To Avoid

- Adding `react-router` or a route table without confirmation
- Assuming a route layer exists because other frontends have one

## Requires Confirmation

- Whether a new routing layer is intended
- Whether an in-app phase is being mistaken for a route

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
- Do not treat the workflow phase as a URL route unless the user explicitly asks for routing.
