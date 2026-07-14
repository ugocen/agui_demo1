---
description: Add a component to the generic A2UI rich catalog
---

## Steps

Generative UI is rendered generically through
`Phase0/frontend/src/components/a2ui/richCatalog.tsx` — adding a UI
capability means extending this catalog, never adding per-agent React cards
(invariant 5).

### 1. Study the existing pattern
- Read `richCatalog.tsx`. It exports `RICH_CATALOG_ID` and a catalog built
  with `createCatalog` from `@copilotkit/a2ui-renderer`. Existing components
  (Mermaid, Chart, Markdown, Html) follow one shape: a `Frame` wrapper, a
  `zod/v3` props schema with `.describe(...)` on every field (schemas use
  `zod/v3`, not the app's default zod v4, because A2UI's `GenericBinder` reads
  zod v3 internals), and heavy browser-only libraries `import()`-ed inside
  `useEffect` so they stay out of SSR and the initial bundle.

### 2. Add the component
- Add a new React component following the `Frame` + `ErrorNote` pattern.
- Register it in the catalog with a `zod/v3` schema — every prop needs
  `.describe(...)` since `includeSchema: true` sends these schemas to the
  agent's LLM so it knows the component exists and what props it takes.

### 3. Verify
```bash
cd Phase0/frontend
npm run build && npm run lint
```

### 4. Report
- Report the component name, the props schema, and the verification result.
