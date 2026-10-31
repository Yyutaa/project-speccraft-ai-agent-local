---
name: repo-coding-template-form-page
description: Discover and apply repository create, edit, and detail form page templates.
---

# Repo Coding Template Form Page

## Purpose

Find the closest same-app form example before creating or restructuring a form page.

## Context Reading

- Read `AGENTS.md` for Repo Guide entry information.
- Read relevant `repo-profile.md` sections for stable facts, modification boundary, commands, shared package scope, app runtime topology, and app-to-package dependency mapping.
- Inspect current repository source files only when evidence is needed.

## Observed Evidence Entry Points

- React: `apps/web/src/GovernanceCreate.tsx`
- React: `apps/web/src/GovernanceResolution.tsx`
- These components build forms from Ant Design `Input`, `Select`, `Radio`, `Checkbox`, and `Button` with local draft state.
- These sampled paths are evidence entry points only. They are not global mandatory implementation rules. Prefer same app, same framework, and same module examples over these anchors when they differ.
- Treat these as lookup anchors, not mandatory global rules, unless the user explicitly confirms them as stable repository-level constraints.

## Framework-Specific Lookup

- React: Inspect `GovernanceCreate.tsx` and `GovernanceResolution.tsx` for field layout, validation, and submit wiring.
- Vue: No evidence found in lightweight sampling
- H5: No evidence found in lightweight sampling

## What To Inspect

- Field composition and validation in `GovernanceCreate.tsx`
- Resolution form flow in `GovernanceResolution.tsx`
- Submit handlers in `App.tsx`

## What To Avoid

- Hand-writing inputs instead of Ant Design primitives
- Duplicating validation already enforced by the backend contract
- Introducing a form library not already installed

## Requires Confirmation

- Whether the target is create, edit, or detail
- Which backend validations are authoritative

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
- Use the evidenced Ant Design primitives first; inline sketches are fallback only.

## React Template

This is a structure sketch only, not copy-ready code.

```text
apps/web/src/<form-module>/
  index.tsx        # page entry
  form-model.ts    # values, defaults, validation mirror
  fields.tsx       # Ant Design Input/Select/Radio groups
```

- Component-library first: Ant Design `Form`, `Input`, `Select`, `Radio`, `Checkbox`, `Button`.
- Linked rule skills: `repo-coding-api`, `repo-coding-components`, `repo-coding-error-code`.

## H5 Template

This is a structure sketch only, not copy-ready code. No H5 surface exists in this repository.

```text
apps/web/src/<mobile-form-module>/
  index.tsx        # mobile form entry
  fields.tsx       # Ant Design Mobile Form/Input placeholders
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
