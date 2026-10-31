---
name: repo-coding-pii
description: Discover and apply sensitive-field, masking, and privacy-boundary rules in this repository.
---

# Repo Coding PII

## Purpose

Identify sensitive content handling before adding display, logging, or export behavior.

## Context Reading

- Read `AGENTS.md` for Repo Guide entry information.
- Read relevant `repo-profile.md` sections for stable facts, modification boundary, commands, shared package scope, app runtime topology, and app-to-package dependency mapping.
- Inspect current repository source files only when evidence is needed.

## Observed Evidence Entry Points

- No evidence found in lightweight sampling
- No masking component or decrypt-view helper was found.
- These sampled paths are evidence entry points only. They are not global mandatory implementation rules. Prefer same app, same framework, and same module examples over these anchors when they differ.
- Treat these as lookup anchors, not mandatory global rules, unless the user explicitly confirms them as stable repository-level constraints.

## Framework-Specific Lookup

- React: No evidence; inspect the touched rendering path only if sensitive fields are involved.
- Vue: No evidence found in lightweight sampling
- H5: No evidence found in lightweight sampling

## What To Inspect

- Whether the touched Run field can contain raw requirement text
- Console/log output in `App.tsx` or `api.ts`

## What To Avoid

- Logging raw requirement or repository text
- Adding client-side decryption or masking that implies a security guarantee

## Requires Confirmation

- Whether the field is considered sensitive
- Whether masking is a product requirement

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
- Do not claim that UI masking provides a security boundary.
