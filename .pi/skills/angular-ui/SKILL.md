---
name: angular-ui
description: pv-control frontend specifics for the Angular v22 app in ui/ (stack, local conventions, angular-cli MCP wiring). Use when editing Angular components, templates, services, forms or tests in ui/, or when building/serving/linting the UI.
---

# Angular UI — `ui/`

Angular **22.2** + TypeScript 6 (`>=6.0 <6.1`), standalone bootstrap, **zoneless**, **no router and no `NgModule`**
(one root `AppComponent` + services), Angular Material/CDK 22, Vitest, SCSS, `strictTemplates`.
Commands live in `AGENTS.md`; only Angular-specific decisions are recorded here.

Framework "how do I do X in Angular v22" is **not** duplicated in this skill — ask the `angular-cli`
MCP (`search_documentation`, `get_best_practices`) instead. What follows is only where this repo's
reality differs from generic advice or where a generic default would be wrong.

## Repo-specific rules

- **Do not add `changeDetection: ChangeDetectionStrategy.OnPush`** to new components — it is the v22
  default (the old `Default` was renamed `Eager`). Existing explicit `OnPush` is harmless; don't churn it.
- **`strictUnclaimedEventNames` is enabled** in `tsconfig.json` — a camelCase `(someEvent)` binding that no
  directive emits and that is not a native DOM event fails compilation. Use kebab-case for custom events
  or wire the binding to a real `@Output()`/listener.
- **Existing legacy forms stay legacy unless asked.** `AppComponent`'s `FormBuilder` controls
  (`chargeModeControl`, `phaseModeControl`, `priorityControl`) are `ReactiveFormsModule`, not signal
  forms. New forms: signal forms. Do not mix migrations into unrelated changes.
- **Do not introduce a router or `NgModule`.** The UI is a single-page dashboard served by FastAPI from
  `ui/dist/ui/browser/`; adding routing/extra build output needs an explicit request.
- Component/directive selectors must use the `app` prefix (`app-foo` element, `appFoo` attribute) —
  angular-eslint fails the build otherwise.
- Styling/markup/log split per file (`.scss` / `.html` / `.ts`); inline templates only for genuinely
  tiny components. Existing code is the style reference: `http-status.service.ts` (`@Service()` +
  readonly signals), `pv-control.service.ts` (typed `HttpClient` wrapper returning Observables).

## `angular-cli` MCP

Configured in repo-root `.mcp.json` as `npx -y @angular/cli mcp` with `cwd: "ui"` (required — that is
the Angular workspace root; running it from the repo root fails).

Use through the `mcp` tool: `mcp({ server: "angular-cli" })` to list, `mcp({ describe: "<tool>" })`
for parameters. Practical points:

- Framework questions → `search_documentation` / `get_best_practices` (current docs, better than
  recalled Angular idioms; also `ai_tutor` for guided learning).
- Build/test/lint → `run_target`; live development → `devserver_start` + `devserver_wait_for_build`,
  and **always `devserver_stop` afterwards**.
- `onpush_zoneless_migration` exists for migrating older apps — not needed here (already v22/zoneless).
- Chain several Angular MCP calls in one go with `mcpScript`.

## Maintenance rule

Keep this skill short and repo-specific. Angular feature news, API surface, and general best practices
belong to the MCP server / angular.dev, not here — if a bullet here restates framework docs, delete it.
