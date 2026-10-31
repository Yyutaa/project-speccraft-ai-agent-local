---
name: repo-coding-template-list-page
description: Discover and apply repository list, table, search, and pagination page templates.
---

# Repo Coding Template List Page

## Purpose

Find the closest same-app list or table example before creating a new list page.

## Context Reading

- Read `AGENTS.md` for Repo Guide entry information.
- Read relevant `repo-profile.md` sections for stable facts, modification boundary, commands, shared package scope, app runtime topology, and app-to-package dependency mapping.
- Inspect current repository source files only when evidence is needed.

## Observed Evidence Entry Points

- No evidence found in lightweight sampling
- No list, table, search, or pagination page was found; the app is a single Run workspace.
- These sampled paths are evidence entry points only. They are not global mandatory implementation rules. Prefer same app, same framework, and same module examples over these anchors when they differ.
- Treat these as lookup anchors, not mandatory global rules, unless the user explicitly confirms them as stable repository-level constraints.

## Framework-Specific Lookup

- React: No same-app list template; `antd` is installed in `apps/web/package.json` and should be the component-library starting point.
- Vue: No evidence found in lightweight sampling
- H5: No evidence found in lightweight sampling

## What To Inspect

- `apps/web/src/App.tsx` for any existing repeated-item rendering
- `apps/web/package.json` for the available component library

## What To Avoid

- Hand-writing table, search, or pagination UI instead of using Ant Design
- Assuming a list template exists
- Building a list page when the request is a single detail form

## Requires Confirmation

- No same-app list template exists; confirm the page structure
- Whether the requested screen is actually a list

## Validation Hints

- `npm --prefix apps/web run typecheck`
- `npm --prefix apps/web run test`
- `npm --prefix apps/web run build`

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
- Use the evidenced component library (Ant Design) first; inline sketches are fallback only.

## React Template

This is a structure sketch only, not copy-ready code.

```text
apps/web/src/<list-module>/
  index.tsx        # page entry, local state and API wiring
  columns.ts       # Ant Design Table column definitions
  filters.ts       # Ant Design Form/Input search model
  components/      # page-local wrappers only
```

- Component-library first: Ant Design `Table`, `Form`, `Input`, `Select`, `Pagination`, `Button`.
- Linked rule skills: `repo-coding-api`, `repo-coding-components`, `repo-coding-enum`.

## H5 Template

This is a structure sketch only, not copy-ready code. No H5 surface exists in this repository.

```text
apps/web/src/<mobile-list-module>/
  index.tsx        # mobile list entry
  list-item.tsx    # Ant Design Mobile List.Item placeholder
```

- Use the same data flow as the React list, but do not add an H5 surface without confirmation.

## Template Application Rules

- Confirm target app/root/framework from `repo-profile.md`.
- Prefer same-app, same-framework examples and evidenced component-library usage over inline structure sketches.
- Do not generate custom hand-written table, form, modal, drawer, list, or bottom-sheet UI as the default implementation.
- Apply template source priority:
  1. User-provided reference module.
  2. Same app + same framework + same page/dialog type examples discovered from current source.
  3. Component-library patterns evidenced by the target repository.
  4. Inline React/H5 structure sketch in this skill.
- Use the inline template only when the target framework is React or H5 and no higher-priority reference is available.
- For Vue targets, do not use the inline React/H5 templates; inspect same-app Vue examples and mark `Requires Confirmation`.
- Do not copy the inline structure sketch directly until same-app examples and evidenced component-library usage have been checked.
- If the inline structure sketch conflicts with a higher-priority reference, prefer the higher-priority reference and report the conflict.
