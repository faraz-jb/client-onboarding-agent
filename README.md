# Client Onboarding Agent

**AI agent that removes client onboarding friction — lead to proposal to delivery.**

Built for the [Google All Things Agentic Hackathon](https://lablab.ai/event/all-things-agentic) — $180K prize pool, deadline **Aug 31 2026**.

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
agent/    # ADK agent core (Phase 1 — Gemini model, tools, workflow)
app/      # Next.js 15 dashboard (Phase 2)
data/     # SQLite DBs (gitignored, never committed)
```

## Setup

```bash
# 1. Clone
git clone https://github.com/faraz-jb/client-onboarding-agent.git
cd client-onboarding-agent

# 2. Environment (Phase 1+)
cp .env.example .env   # fill GEMINI_API_KEY

# 3. Python venv (Phase 1+)
python -m venv .venv
pip install google-adk google-genai

# 4. Run agent (Phase 1+)
python -m agent.agent
```

## Security

- Real API keys live **only** in local `.env` — never committed (`.env`, `.env.*` gitignored).
- Real client data never enters the repo — `data/` and `*.db` are gitignored.
- `.env.example` ships with empty values as a template.

## Phases

- **Phase 0** — project skeleton (current)
- **Phase 1** — ADK agent core: lead intake, qualification, proposal builder, delivery handoff
- **Phase 2** — Next.js 15 dark-theme dashboard

## Hackathon

[Google All Things Agentic Hackathon](https://lablab.ai/event/all-things-agentic) — LabLab x Google.
