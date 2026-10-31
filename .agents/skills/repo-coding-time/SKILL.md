---
name: repo-coding-time
description: Discover and apply time-display, timezone, and timestamp-conversion rules in this repository.
---

# Repo Coding Time

## Purpose

Find the existing time representation before formatting timestamps or changing timezone behavior.

## Context Reading

- Read `AGENTS.md` for Repo Guide entry information.
- Read relevant `repo-profile.md` sections for stable facts, modification boundary, commands, shared package scope, app runtime topology, and app-to-package dependency mapping.
- Inspect current repository source files only when evidence is needed.

## Observed Evidence Entry Points

- No evidence found in lightweight sampling
- No date/time utility or timezone helper was found in the frontend source.
- These sampled paths are evidence entry points only. They are not global mandatory implementation rules. Prefer same app, same framework, and same module examples over these anchors when they differ.
- Treat these as lookup anchors, not mandatory global rules, unless the user explicitly confirms them as stable repository-level constraints.

## Framework-Specific Lookup

- React: No evidence; inspect the API payload field if a timestamp is displayed.
- Vue: No evidence found in lightweight sampling
- H5: No evidence found in lightweight sampling

## What To Inspect

- Timestamp fields in `apps/web/src/api.ts` types
- Any existing display formatting in `App.tsx`

## What To Avoid

- Inventing timezone conversion rules
- Formatting server timestamps differently across components

## Requires Confirmation

- The expected display timezone and format
- Whether the server already returns a display-ready value

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
- Prefer a single formatting helper once more than one component displays time.
