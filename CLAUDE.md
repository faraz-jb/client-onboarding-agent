# CLAUDE.md — Client Onboarding Agent

## Project
AI agent that removes client onboarding friction — lead to proposal to delivery.
Built for the Google All Things Agentic Hackathon ($180K prize pool, deadline Aug 31 2026).

## Stack
- **Agent runtime:** Google ADK (Agent Development Kit) — Python, `agent/` package
- **LLM:** Gemini API (key via `GEMINI_API_KEY` in `.env` only)
- **Frontend:** Next.js 15 (App Router) — dark theme dashboard, ships Phase 2 (`app/`)
- **Persistence:** SQLite (`data/`) — local file DB, gitignored

## UI Theme (dark, AI Invention brand)
- Background: `#03050a`
- Primary accent: `#22d3ee` (cyan)
- Secondary accent: `#2ef2c3` (teal)
- Professional/luxury style — never playful

## Security-First Rules
- **NEVER hardcode API keys or secrets** in any committed file.
- Real keys live only in local `.env` (gitignored). `.env.example` holds keys with empty values.
- Real client data never enters the repo: `data/`, `*.db`, `*.sqlite*` are gitignored.
- No placeholder/fake data in committed code — real structure, real logic, real data only.
- Code comments in English.

## Git Rules
- NEVER commit: `.env`, `.env.local`, `node_modules/`, `.next/`, `out/`, `data/`, `*.db`, `__pycache__/`, `.venv/`
- Branch: `main` only. Commit messages: conventional (`feat:`, `chore:`, `fix:`).

## Phases
- **Phase 0 (current):** project skeleton — repo layout, git, docs.
- **Phase 1:** ADK agent core — Gemini model, tool registry, onboarding workflow (lead → qualify → propose → delivery handoff).
- **Phase 2:** Next.js 15 dashboard — dark theme UI, onboarding status, proposal preview.

## Dev Workflow
- Agent logic (`agent/agent.py` + tools) lands in Phase 1 — TODO stubs only in this phase.
- `python -m agent.agent` = Phase 1 entrypoint (NotImplementedError until wired).
- Run/verify: `git status` clean before and after every change.
