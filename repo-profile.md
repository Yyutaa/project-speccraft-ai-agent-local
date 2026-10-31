# Repo Profile

## Profile

- Repo name: SpecCraft AI Agent
- Repo type: Full-stack AI agent teaching project with one React frontend app
- Last verified at: 2026-10-31

## Frontend App Repo Classification

- Repo kind: single-app
- Frameworks:
  - React: yes
  - Vue: no
  - H5: no
- App / framework map:
  - App/root: `apps/web`
    - Framework: React
    - Role: PC web workspace UI; portal/service ownership unknown
    - Source roots:
      - `apps/web/src`

## Business Scope

### PC

- Business scope:
  - 需求来源候选、知识/假设治理、澄清与决策
  - PRD/TD 编制、人工审阅、审批与 DeliverySpec 投影展示
  - 单 Run 的内存演示工作台
- Service portals:
  - Portal: unknown
    - Apps:
      - `apps/web`

### Mobile

- Business scope:
  - Not applicable — no mobile surface exists in this repository.
- Service apps:
  - Not applicable.

## Commands

### Install

- Command: `npm --prefix apps/web install`
- CWD: .

### Dev / Serve

- `apps/web`:
  - Command: `npm --prefix apps/web run dev`
  - Example: `VITE_API_TARGET=http://127.0.0.1:8765 npm --prefix apps/web run dev`
  - Note: Vite proxies `/api` to `VITE_API_TARGET ?? http://127.0.0.1:8765`; the dev port is not explicitly configured, so the Vite default applies.

### Build

- Command: `npm --prefix apps/web run build`

### Lint

- No frontend lint command found in lightweight sampling; `apps/web/package.json` defines no lint script.

### Test / Typecheck

- Command: `npm --prefix apps/web run test`
- Command: `npm --prefix apps/web run typecheck`

## Shared Package Scope

- Package: No JavaScript/TypeScript shared package exists in this repository.
  - Framework surface: N/A
  - Serves apps:
    - N/A
  - Scope:
    - `packages/contracts`, `packages/agent-kernel`, and `packages/speccraft` are Python backend packages. They do not serve the React app as frontend shared packages.
- Mobile shared package status:
  - Not applicable — no mobile surface.

## App Runtime Topology

- Runtime type: single React app with a separately started Python API
- App: `apps/web`
  - Portal: unknown
  - Service app: N/A
  - Runtime role:
    - Browser SPA served by Vite in development; static output lands in `apps/web/dist` after build.
  - Dependency:
    - A FastAPI backend must be reachable at `http://127.0.0.1:8765` for `/api/*` requests.
  - Startup linkage example:
    - 1. Start the API so `http://127.0.0.1:8765` is available (see `Makefile` target `run-api`).
    - 2. Start the web app with `npm --prefix apps/web run dev`.
  - Notes:
    - `apps/web/vite.config.ts` rewrites `/api` through the configured proxy target.
    - No authentication is implemented; Run state lives in the API process memory.
    - The frontend has no router; `apps/web/src/App.tsx` and `apps/web/src/governance.ts` render the workflow phases.

## App-to-Package Dependency Map

- No frontend app-to-shared-package map exists:
  - `apps/web` does not import from `packages/*`; it talks to the backend over HTTP only.
- Cross-framework shared usage exists:
  - no
- Mobile dependency status:
  - Not applicable — no mobile surface.

## Modification Boundary

- Treat `apps/web/src/api.ts` as the single frontend API boundary; backend request/response contracts live in `packages/contracts` and are out of frontend scope.
- This repository has one frontend app, one framework (React), and no shared frontend packages; prefer same-app, same-framework, same-module examples over generic cross-app examples.
- There is no router or menu layer; do not invent route registration or portal-entry rules. Render state from server projections in `apps/web/src/App.tsx` and `apps/web/src/governance.ts`.
- Python backend, CLI, Worker, and contract changes are outside the Repo Guide frontend skill scope; follow the backend rules recorded in `AGENTS.md`.
- Do not write request-time scan results, change targets, diff impact, or validation results into `AGENTS.md` or `repo-profile.md`.
- Keep request-time findings out of this file.
