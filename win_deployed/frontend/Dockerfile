# ---------- Frontend: Next.js 16 Standalone ----------
#
# Requires `output: "standalone"` in next.config.ts.
#
# This app talks to the backend over TWO different URLs, and mixing them up is
# the easiest way to ship a broken image:
#
#   NEXT_PUBLIC_BACKEND_URL — read in the BROWSER (src/lib/config.ts) for
#     /api/me, /api/agents, /api/agui/<id>/health and the admin screen. It is
#     baked into the client bundle at BUILD time and must be a URL a user's
#     browser can resolve — the backend's public ingress hostname. An in-cluster
#     Service DNS name like http://agui-backend:8000 does NOT work here.
#   BACKEND_URL — read at RUNTIME by the server-side route handler
#     (src/app/api/copilotkit/[[...path]]/route.ts) that carries the AG-UI SSE
#     stream. This one is in-cluster and belongs in the pod's env, not here.
#
# Build, for an Entra/SSO deployment:
#   docker build \
#     --build-arg NEXT_PUBLIC_AUTH_MODE=entra \
#     --build-arg NEXT_PUBLIC_BACKEND_URL=https://agui-api.example.internal \
#     --build-arg NEXT_PUBLIC_ENTRA_TENANT_ID=<tenant> \
#     --build-arg NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID=<client> \
#     -t agui-frontend .
#
# Then run it with BACKEND_URL=http://agui-backend:8000 in the container env.

# ---- Stage 1: install dependencies ----
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# --ignore-scripts: no dependency in package.json needs a postinstall build step,
# and blocking them keeps an install script out of the build. If a future
# dependency does need one (a native module such as sharp), this flag is where
# the build will fail — drop it for that package rather than debugging Next.js.
RUN npm ci --ignore-scripts

# ---- Stage 2: build ----
FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build-time env vars — baked into the client bundle via next.config.ts `env`.
# Override per environment at `docker build` time.
#
# AUTH_MODE defaults to `iam` to match next.config.ts's own fallback, so a bare
# `docker build .` produces a coherent (SSO-off) image. It previously defaulted
# to `entra` while the tenant/client ids defaulted to empty strings, which built
# an image that looked configured, passed the build, and then failed in the
# browser at MSAL init. The guard below makes that combination fail here instead.
ARG NEXT_PUBLIC_AUTH_MODE=iam
ARG NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
ARG NEXT_PUBLIC_ENTRA_TENANT_ID=""
ARG NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID=""
ARG NEXT_PUBLIC_ENTRA_ALLOWED_AUDIENCE=""

RUN if [ "$NEXT_PUBLIC_AUTH_MODE" = "entra" ] && \
       { [ -z "$NEXT_PUBLIC_ENTRA_TENANT_ID" ] || [ -z "$NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID" ]; }; then \
      echo "FAIL: NEXT_PUBLIC_AUTH_MODE=entra needs both NEXT_PUBLIC_ENTRA_TENANT_ID" >&2; \
      echo "      and NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID as --build-arg. They are baked" >&2; \
      echo "      into the client bundle, so they cannot be supplied at run time." >&2; \
      exit 1; \
    fi

ENV NEXT_PUBLIC_AUTH_MODE=$NEXT_PUBLIC_AUTH_MODE \
    NEXT_PUBLIC_BACKEND_URL=$NEXT_PUBLIC_BACKEND_URL \
    NEXT_PUBLIC_ENTRA_TENANT_ID=$NEXT_PUBLIC_ENTRA_TENANT_ID \
    NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID=$NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID \
    NEXT_PUBLIC_ENTRA_ALLOWED_AUDIENCE=$NEXT_PUBLIC_ENTRA_ALLOWED_AUDIENCE

RUN npm run build

# ---- Stage 3: production runner ----
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# .next/standalone does NOT include public/ or .next/static — copy both.
# This is a known Next.js behavior, not optional.
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000 \
    HOSTNAME="0.0.0.0"

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000/ || exit 1

CMD ["node", "server.js"]
