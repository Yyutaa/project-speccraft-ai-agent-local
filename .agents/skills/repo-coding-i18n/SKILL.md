---
name: repo-coding-i18n
description: Discover and apply translation-key, locale-resource, and text-rendering rules in this repository.
---

# Repo Coding I18n

## Purpose

Determine whether a localization system exists before changing or extracting user-facing text.

## Context Reading

- Read `AGENTS.md` for Repo Guide entry information.
- Read relevant `repo-profile.md` sections for stable facts, modification boundary, commands, shared package scope, app runtime topology, and app-to-package dependency mapping.
- Inspect current repository source files only when evidence is needed.

## Observed Evidence Entry Points

- No evidence found in lightweight sampling
- UI copy is currently inline Chinese in `apps/web/src/App.tsx` and governance components; no locale files or translation wrapper were found.
- These sampled paths are evidence entry points only. They are not global mandatory implementation rules. Prefer same app, same framework, and same module examples over these anchors when they differ.
- Treat these as lookup anchors, not mandatory global rules, unless the user explicitly confirms them as stable repository-level constraints.

## Framework-Specific Lookup

- React: No evidence; inspect the touched component's inline copy only if a text change is requested.
- Vue: No evidence found in lightweight sampling
- H5: No evidence found in lightweight sampling

## What To Inspect

- The touched component's inline text when the request is text-only
- `apps/web/package.json` if adding an i18n dependency is proposed

## What To Avoid

- Inventing locale directories or translation keys
- Mixing a new i18n system into unrelated changes

## Requires Confirmation

- Whether the repository should introduce i18n at all
- Whether existing inline Chinese text is an intentional product choice

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
- Do not present a new i18n framework as the default solution when none exists.
