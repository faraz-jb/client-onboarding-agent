# syntax=docker/dockerfile:1

# Two runtimes in one image:
#   - Next.js 15 standalone server (UI + API routes) -> node /app/server.js
#   - Python ADK agent, spawned per lead by POST /api/agent/process-lead as
#     `<cwd>/.venv/bin/python -m agent.agent --lead-id <id>` with cwd = /app.
#
# That spawn is why WORKDIR /app is mandatory and why .venv/ and agent/ must
# sit directly under /app, as siblings of server.js.

# ---------- base: Node 22 + a Python venv holding the agent's dependencies ----------
FROM node:22-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 \
      python3-venv \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Path is load-bearing: process-lead resolves exactly /app/.venv/bin/python and
# returns a 500 if it is missing.
RUN python3 -m venv /app/.venv

COPY requirements.txt ./
RUN /app/.venv/bin/pip install --no-cache-dir --upgrade pip \
 && /app/.venv/bin/pip install --no-cache-dir -r requirements.txt

# ---------- build: compile the Next.js standalone bundle ----------
FROM base AS build

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ---------- runner: standalone server + agent + venv ----------
# Inherits the Linux venv from `base`, so .venv is never copied across stages
# (copying the host's .venv would drop Windows binaries into a Linux image —
# .dockerignore excludes it from the build context for the same reason).
FROM base AS runner

WORKDIR /app

ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000

# Standalone emits server.js plus its traced node_modules at the root.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static

# The Python side of the pipeline.
COPY --from=build /app/agent ./agent

# Reference template only — real values arrive as environment variables.
COPY .env.example ./.env.example

# SQLite lives here, bind-mounted in compose. Both runtimes must agree on this
# path: Node reads DB_PATH, while agent/memory.py derives <agent/>/../data,
# which resolves to /app/data only because agent/ sits at /app/agent.
#
# The rm is deliberate. Next.js output-file-tracing sweeps data/onboarding.db
# into .next/standalone/ when a database exists at build time, so the COPY
# above can carry real client data into an image layer. .dockerignore already
# keeps data/ out of the build context; this makes the guarantee unconditional
# rather than dependent on that file staying correct.
RUN rm -rf /app/data && mkdir -p /app/data

EXPOSE 3000

# Node 22 has global fetch, so the check needs no extra package. `/` is the
# public landing page — it is not behind the auth middleware.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
