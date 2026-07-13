"use client";

import {
  A2UIProvider,
  A2UIRenderer,
  injectStyles,
  type OnActionCallback,
  useA2UI,
} from "@copilotkit/a2ui-renderer";
import { useEffect } from "react";

/** One A2UI v0.9 message (createSurface / updateComponents / updateDataModel / …). */
export type A2UIOperation = Record<string, unknown>;

function SurfaceFeeder({
  surfaceId,
  operations,
}: {
  surfaceId: string;
  operations: A2UIOperation[];
  // catalog is consumed by the A2UIProvider above; kept out of this inner comp.
}) {
  const { processMessages } = useA2UI();

  // Feed the v0.9 operation stream into the renderer. Re-runs when new ops arrive
  // (e.g. an agent streaming updateComponents/updateDataModel to the same surface).
  useEffect(() => {
    if (operations.length > 0) {
      processMessages(operations);
    }
  }, [operations, processMessages]);

  return (
    <A2UIRenderer
      surfaceId={surfaceId}
      fallback={<div style={{ color: "var(--text-muted)", fontSize: 13 }}>Rendering A2UI surface…</div>}
    />
  );
}

/**
 * Renders an A2UI surface from a list of v0.9 operations, using the renderer's
 * built-in basic catalog. This is the "A2UI render" path — the UI is described by
 * the agent as JSON and painted here, instead of a hand-authored React card.
 */
export function A2UISurfaceView({
  surfaceId,
  operations,
  onAction,
  catalog,
}: {
  surfaceId: string;
  operations: A2UIOperation[];
  onAction?: OnActionCallback;
  /** Optional component catalog. When omitted, the renderer's basic catalog is used. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  catalog?: any;
}) {
  useEffect(() => {
    // Inject the renderer's component styles once (idempotent).
    injectStyles();
  }, []);

  return (
    <A2UIProvider onAction={onAction} catalog={catalog}>
      <SurfaceFeeder surfaceId={surfaceId} operations={operations} />
    </A2UIProvider>
  );
}
