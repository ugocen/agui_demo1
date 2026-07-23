import type { NextConfig } from "next";
import path from "node:path";
import { loadEnvFile } from "node:process";

// Config source depends on the layout this app is checked out in:
//  * Monorepo (Phase0/frontend): the repo-root Phase0/.env supplies the
//    non-prefixed vars (AUTH_MODE, BACKEND_URL, ENTRA_*) loaded here.
//  * Standalone (own repo, e.g. the enterprise deployment): there is no ../.env;
//    config comes from this app's own .env.local as NEXT_PUBLIC_* vars.
// Each entry in `env` below therefore falls back non-prefixed -> NEXT_PUBLIC_ ->
// default. The fallback is load-bearing: keys listed in `env` OVERRIDE .env.local,
// so without it a standalone checkout would silently ignore .env.local and boot
// with AUTH_MODE=iam (SSO off). Verified by build test.
try {
  loadEnvFile(path.resolve(process.cwd(), "../.env"));
} catch {
  // .env not present (standalone layout) — NEXT_PUBLIC_* from .env.local is used
}

const nextConfig: NextConfig = {
  // Produce a self-contained server.js under .next/standalone/ so the app can
  // run inside a container without the full node_modules tree. Required for
  // the Docker/EKS deployment; harmless for local dev (`next dev` ignores it).
  output: "standalone",
  // Pin the Turbopack workspace root to this app. Without it, Next.js walks up
  // the directory tree, finds an unrelated package-lock.json in a parent folder
  // (e.g. ~/projects) and infers the wrong root — widening dev-server file
  // watching and emitting the "inferred your workspace root" build warning.
  // process.cwd() is this frontend dir (same assumption the .env load above
  // relies on), where this app's own package-lock.json lives.
  turbopack: {
    root: process.cwd(),
  },
  env: {
    NEXT_PUBLIC_AUTH_MODE: process.env.AUTH_MODE ?? process.env.NEXT_PUBLIC_AUTH_MODE ?? "iam",
    NEXT_PUBLIC_BACKEND_URL:
      process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000",
    NEXT_PUBLIC_ENTRA_TENANT_ID:
      process.env.ENTRA_TENANT_ID ?? process.env.NEXT_PUBLIC_ENTRA_TENANT_ID ?? "",
    NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID:
      process.env.ENTRA_SPA_CLIENT_ID ?? process.env.NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID ?? "",
    NEXT_PUBLIC_ENTRA_ALLOWED_AUDIENCE:
      process.env.ENTRA_ALLOWED_AUDIENCE ?? process.env.NEXT_PUBLIC_ENTRA_ALLOWED_AUDIENCE ?? "",
  },
};

export default nextConfig;
