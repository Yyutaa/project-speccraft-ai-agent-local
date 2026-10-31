---
name: repo-coding-template-dialog
description: Discover and apply repository modal, drawer, confirm, and batch-operation dialog templates.
---

# Repo Coding Template Dialog

## Purpose

Find the closest same-app dialog example before adding a modal, drawer, or confirmation flow.

## Context Reading

- Read `AGENTS.md` for Repo Guide entry information.
- Read relevant `repo-profile.md` sections for stable facts, modification boundary, commands, shared package scope, app runtime topology, and app-to-package dependency mapping.
- Inspect current repository source files only when evidence is needed.

## Observed Evidence Entry Points

- No evidence found in lightweight sampling
- No `Modal`, `Drawer`, or confirmation-dialog usage was found; `antd` is installed and is the component-library starting point.
- These sampled paths are evidence entry points only. They are not global mandatory implementation rules. Prefer same app, same framework, and same module examples over these anchors when they differ.
- Treat these as lookup anchors, not mandatory global rules, unless the user explicitly confirms them as stable repository-level constraints.

## Framework-Specific Lookup

- React: No same-app dialog example; start from Ant Design `Modal` or `Drawer` and confirm placement with the user.
- Vue: No evidence found in lightweight sampling
- H5: No evidence found in lightweight sampling

## What To Inspect

- `apps/web/src/App.tsx` for existing inline confirmation patterns
- `apps/web/package.json` for the available component library

## What To Avoid

- Hand-writing modal or drawer UI
- Assuming a dialog layer exists
- Using a dialog for a full-page workflow step

## Requires Confirmation

- No same-app dialog template exists; confirm placement and trigger
- Whether the flow should be a dialog or a full page

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
apps/web/src/<dialog-module>/
  dialog.tsx       # Ant Design Modal/Drawer wrapper
  content.tsx      # form or confirmation body
```

- Component-library first: Ant Design `Modal`, `Drawer`, `Button`, `Space`.
- Linked rule skills: `repo-coding-components`, `repo-coding-template-form-page`, `repo-coding-error-code`.

## H5 Template

This is a structure sketch only, not copy-ready code. No H5 surface exists in this repository.

```text
apps/web/src/<mobile-dialog-module>/
  sheet.tsx        # Ant Design Mobile Popup placeholder
```

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
