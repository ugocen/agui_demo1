---
description: Add a component to the generic A2UI rich catalog
argument-hint: <component name and what it renders, e.g. "Timeline of dated events">
---

Add a new A2UI component: $ARGUMENTS

Launch the `a2ui-component-builder` subagent to add it to
`Phase0/frontend/src/components/a2ui/richCatalog.tsx` end to end, following
the established pattern (Mermaid/Chart/Markdown/Html): a `Frame`-wrapped
component, a `zod/v3` props schema with `.describe(...)` on every field, and
`import()`-ed browser-only libraries inside `useEffect`. This extends the
generic catalog — never add per-agent React cards. Have it verify with `cd
Phase0/frontend && npm run build && npm run lint`, then summarize. Do not
commit unless I ask.
