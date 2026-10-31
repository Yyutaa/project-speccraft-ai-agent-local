---
name: repo-coding-store
description: Discover and apply state-management, store-boundary, and state-ownership rules in this repository.
---

# Repo Coding Store

## Purpose

Identify the real state ownership model before moving or sharing state.

## Context Reading

- Read `AGENTS.md` for Repo Guide entry information.
- Read relevant `repo-profile.md` sections for stable facts, modification boundary, commands, shared package scope, app runtime topology, and app-to-package dependency mapping.
- Inspect current repository source files only when evidence is needed.

## Observed Evidence Entry Points

- React: `apps/web/src/App.tsx`
- React: `apps/web/src/TdGovernance.tsx`
- State is local React `useState`; no Redux, Zustand, or other store library is installed or imported.
- These sampled paths are evidence entry points only. They are not global mandatory implementation rules. Prefer same app, same framework, and same module examples over these anchors when they differ.
- Treat these as lookup anchors, not mandatory global rules, unless the user explicitly confirms them as stable repository-level constraints.

## Framework-Specific Lookup

- React: Inspect `useState` usage in `apps/web/src/App.tsx` and local form state in governance components.
- Vue: No evidence found in lightweight sampling
- H5: No evidence found in lightweight sampling

## What To Inspect

- `useState` / `useEffect` boundaries in `App.tsx`
- Props flow into `GovernanceCreate`, `GovernanceResolution`, and `TdGovernance`
- `Run` response as the authoritative state source

## What To Avoid

- Introducing a global store without confirmation
- Duplicating server Run state in client-side derived state
- Moving workflow state ownership into the browser

## Requires Confirmation

- Whether state must be shared across components
- Whether a new store dependency is justified

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
- The narrowest state is local component state; escalate only when cross-component sharing is proven.
