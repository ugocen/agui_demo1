import type { NextConfig } from "next";
import path from "node:path";
import { loadEnvFile } from "node:process";

// Configuration comes only from Phase0/.env (doc 07 section 0 rule).
try {
  loadEnvFile(path.resolve(process.cwd(), "../.env"));
} catch {
  // .env not present yet, defaults below keep local dev working
}

const nextConfig: NextConfig = {
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
    NEXT_PUBLIC_AUTH_MODE: process.env.AUTH_MODE ?? "iam",
    NEXT_PUBLIC_BACKEND_URL: process.env.BACKEND_URL ?? "http://localhost:8000",
    NEXT_PUBLIC_ENTRA_TENANT_ID: process.env.ENTRA_TENANT_ID ?? "",
    NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID: process.env.ENTRA_SPA_CLIENT_ID ?? "",
    NEXT_PUBLIC_ENTRA_ALLOWED_AUDIENCE: process.env.ENTRA_ALLOWED_AUDIENCE ?? "",
  },
};

export default nextConfig;
