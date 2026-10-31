---
name: repo-coding-menu
description: Discover and apply menu, navigation, sidebar, and portal-entry rules in this repository.
---

# Repo Coding Menu

## Purpose

Locate the repository's real navigation or menu surfaces before changing phase navigation, workspace navigation, or portal-entry behavior.

## Context Reading

- Read `AGENTS.md` for Repo Guide entry information.
- Read relevant `repo-profile.md` sections for stable facts, modification boundary, commands, shared package scope, app runtime topology, and app-to-package dependency mapping.
- Inspect current repository source files only when evidence is needed.

## Observed Evidence Entry Points

- React: `apps/web/src/App.tsx`
- React: `apps/web/src/main.tsx`
- No menu, sidebar, portal-entry, or router config exists; navigation is rendered inline by the single `App` component.
- These sampled paths are evidence entry points only. They are not global mandatory implementation rules. Prefer same app, same framework, and same module examples over these anchors when they differ.
- Treat these as lookup anchors, not mandatory global rules, unless the user explicitly confirms them as stable repository-level constraints.

## Framework-Specific Lookup

- React: Inspect the phase/workspace rendering in `apps/web/src/App.tsx`; there is no menu registration layer to extend.
- Vue: No evidence found in lightweight sampling
- H5: No evidence found in lightweight sampling

## What To Inspect

- `apps/web/src/App.tsx` phase display and command visibility
- `Run.available_commands` handling before adding any navigation affordance

## What To Avoid

- Inventing a sidebar or portal config that does not exist
- Letting client-side navigation decide workflow phases

## Requires Confirmation

- Whether a new navigation surface is actually required
- Whether the change is a workflow phase or a real menu item

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
- Menu or navigation state must follow server projections, not client-authored workflow logic.
