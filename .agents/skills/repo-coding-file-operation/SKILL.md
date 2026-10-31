---
name: repo-coding-file-operation
description: Discover and apply upload, download, import, export, and blob-handling rules in this repository.
---

# Repo Coding File Operation

## Purpose

Find the real file-flow boundary before adding upload, download, or export behavior.

## Context Reading

- Read `AGENTS.md` for Repo Guide entry information.
- Read relevant `repo-profile.md` sections for stable facts, modification boundary, commands, shared package scope, app runtime topology, and app-to-package dependency mapping.
- Inspect current repository source files only when evidence is needed.

## Observed Evidence Entry Points

- No evidence found in lightweight sampling
- No upload/download helper or blob handling was found. Requirement-file access is a server-side path field, not a browser upload.
- These sampled paths are evidence entry points only. They are not global mandatory implementation rules. Prefer same app, same framework, and same module examples over these anchors when they differ.
- Treat these as lookup anchors, not mandatory global rules, unless the user explicitly confirms them as stable repository-level constraints.

## Framework-Specific Lookup

- React: No evidence; inspect `api.ts` request types if a file field is involved.
- Vue: No evidence found in lightweight sampling
- H5: No evidence found in lightweight sampling

## What To Inspect

- `apps/web/src/api.ts` for any file-related request field
- `apps/web/src/App.tsx` for path-input handling

## What To Avoid

- Building a browser file upload when the contract expects a server-side relative path
- Reading local absolute paths from the browser

## Requires Confirmation

- Whether the flow is upload or server-side path selection
- Allowed file types and size limits from the backend contract

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
- File path safety is enforced by the backend; the frontend must not pretend to authorize paths.
