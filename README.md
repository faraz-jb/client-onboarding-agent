# Client Onboarding Agent

**AI agent that removes client onboarding friction — lead to proposal to delivery.**

Built for the [Google All Things Agentic Hackathon](https://allthingsagentichackathon.devpost.com) — $180K prize pool, deadline **Aug 31 2026**.

## Stack

![Google ADK](https://img.shields.io/badge/Google%20ADK-Python-4285F4)
![Gemini API](https://img.shields.io/badge/Gemini%20API-LLM-8E75B2)
![Next.js](https://img.shields.io/badge/Next.js-15-000000)
![SQLite](https://img.shields.io/badge/SQLite-local-003B57)

| Layer | Tech |
| --- | --- |
| Agent runtime | Google ADK (Agent Development Kit) — Python |
| LLM | Gemini API |
| Frontend | Next.js 15 (App Router) — dark theme dashboard |
| Persistence | SQLite (local `data/`) |

## What It Does

An agent that carries a client from first lead to proposal to delivery handoff —
removing the manual friction of onboarding: intake → qualification → proposal → kickoff.

## Project Layout

```
agent/       # ADK agent core (Phase 1 — Gemini model, tools, workflow)
app/         # Next.js 15 App Router — landing page, dashboard, API routes (Phase 2)
components/  # Client-side UI components (Phase 2)
lib/         # SQLite data access (node:sqlite) + formatting helpers (Phase 2)
data/        # SQLite DBs (gitignored, never committed)
```

## Setup

```bash
# 1. Clone
git clone https://github.com/faraz-jb/client-onboarding-agent.git
cd client-onboarding-agent

# 2. Environment — required, the app fails closed without these
cp .env.example .env

# 3. Python venv (Phase 1+)
python -m venv .venv
.venv/Scripts/activate   # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt

# 4. Run tests (no API key needed)
python -m agent.test_agent

# 5. Run agent — dry-run (structure only, no Gemini call)
python -m agent.agent --lead '{"name": "Test Client", "email": "test@example.com", "service": "AI Website", "budget": 5000}' --dry-run

# 6. Run agent — live (needs GEMINI_API_KEY in .env)
python -m agent.agent --lead '{"name": "Test Client", "email": "test@example.com", "service": "AI Website", "budget": 5000}'

# 7. Dashboard UI (Phase 2+) — requires Node 22+ (node:sqlite)
npm install
npm run dev      # http://localhost:3000 — landing page + /dashboard
npm run build    # production build (standalone output)
```

Open <http://localhost:3000/login> — log in with `ADMIN_PASSWORD` to reach `/dashboard`.

### Required environment variables

Fill all six in `.env` after copying the template. Missing auth vars mean auth
fails closed: every protected route denies and the dashboard is unreachable.

| Variable | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Real Gemini API key |
| `GEMINI_BRAIN_MODEL` | Brain-tier model — the default in `.env.example` is fine |
| `GEMINI_FAST_MODEL` | Fast-tier model — the default in `.env.example` is fine |
| `ADMIN_PASSWORD` | Admin login password |
| `ADMIN_PASSWORD_SALT` | Random hex, ≥16 chars — generate once, then leave it alone |
| `SESSION_SECRET` | Random hex, ≥32 chars — generate once; rotating it invalidates all sessions |

`ADMIN_PASSWORD_SALT` and `SESSION_SECRET` can be generated with: `openssl rand -hex 32`

## Security

- Real API keys live **only** in local `.env` — never committed (`.env`, `.env.*` gitignored).
- Real client data never enters the repo — `data/` and `*.db` are gitignored.
- `.env.example` ships with empty values as a template.
- Dashboard and agent-trigger endpoints require admin login (scrypt password + HMAC-signed session cookie, httpOnly).

## Phases

- **Phase 0** — project skeleton
- **Phase 1** — ADK agent core: lead intake, qualification, proposal builder, delivery handoff
- **Phase 2** — Next.js 15 dark-theme dashboard + API routes
- **Phase 3** — live Gemini pipeline: classify → proposal writer → delivery plan → notify (Telegram)
- **Phase 4** — security hardening: admin auth (scrypt + HMAC session), rate limiting, audit log
- **Phase 5** — VPS deploy + demo (next)

## Hackathon

[Google All Things Agentic Hackathon](https://allthingsagentichackathon.devpost.com)
