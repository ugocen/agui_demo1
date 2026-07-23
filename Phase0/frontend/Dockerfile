# ---------- Frontend: Next.js 16 Standalone ----------
#
# Requires `output: "standalone"` in next.config.ts.
#
# Build-time env: keys in next.config.ts `env` block are baked at build time.
# Pass them as --build-arg to docker build, e.g.:
#   docker build \
#     --build-arg NEXT_PUBLIC_AUTH_MODE=entra \
#     --build-arg NEXT_PUBLIC_BACKEND_URL=http://agui-backend:8000 \
#     --build-arg NEXT_PUBLIC_ENTRA_TENANT_ID=<tenant> \
#     --build-arg NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID=<client> \
#     -t agui-frontend .

# ---- Stage 1: install dependencies ----
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

# ---- Stage 2: build ----
FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build-time env vars — baked into the image via next.config.ts `env` block.
# Override per environment at `docker build` time.
ARG NEXT_PUBLIC_AUTH_MODE=entra
ARG NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
ARG NEXT_PUBLIC_ENTRA_TENANT_ID=""
ARG NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID=""
ARG NEXT_PUBLIC_ENTRA_ALLOWED_AUDIENCE=""

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
