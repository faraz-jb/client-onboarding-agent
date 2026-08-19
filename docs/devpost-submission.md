# Devpost submission — copy-paste text

Ready-to-paste copy for the Devpost form. Everything below describes what the
repo actually does.

---

## Project name

```
Client Onboarding Agent
```

## Tagline

```
AI agent that removes client onboarding friction — lead to proposal to delivery
```

## Elevator pitch

```
Every agency loses deals in the gap between "someone filled in the contact form"
and "here is your proposal" — a gap measured in days of manual triage, copy
writing, and follow-up. Client Onboarding Agent closes it: a lead submitted on
the public form is classified, turned into a written proposal, given a delivery
plan, and notified on — autonomously, in seconds. Every step is recorded in an
append-only audit trail, so the business can see exactly what the agent did and
why.
```

---

## Full description

### The problem

Client onboarding is where small agencies quietly bleed revenue. A lead arrives
and then waits: someone has to judge whether it is worth pursuing, write a
proposal that reflects what the client actually asked for, sketch a delivery
plan, and reply before the lead goes cold. It is repetitive, it is judgement
work, and it is exactly the sort of thing that slips when the team is busy
delivering. The cost is invisible — you never see the deal you lost because the
proposal took four days.

### The solution

An agent pipeline that carries a lead from first contact to a delivery-ready
proposal without a human in the loop:

1. **Intake** — the public form validates and stores the lead.
2. **Classify** — a fast Gemini sub-agent scores priority as hot / warm / cold.
3. **Propose** — a brain-tier Gemini sub-agent writes real overview, scope,
   timeline, and pricing copy grounded strictly in what the client stated.
4. **Plan** — a delivery plan is generated: discovery → build → review → handover.
5. **Notify** — a Telegram message goes out with the lead and its priority.

The dashboard shows all of it live, including the audit log — the agent's work
is inspectable, not a black box.

### Key features

- **Autonomous multi-step pipeline** — one lead id in, a classified lead, a
  written proposal, a delivery plan, and a sent notification out.
- **Two-tier model placement** — a fast model for classification and
  extraction, a brain-tier model for proposal writing. Neither is hardcoded;
  both come from environment configuration.
- **Graceful offline degradation** — with no API key the pipeline runs a
  deterministic heuristic path. The product demos and its tests pass with no
  network and no credentials.
- **Append-only audit trail** — every action *and every rejection* writes an
  `agent_log` row. The dashboard renders it as a first-class view.
- **Security-first admin layer** — scrypt password derivation, HMAC-signed
  session cookies, per-IP rate limiting, and fail-closed behaviour when
  unconfigured.
- **Live status tracking** — the intake form polls the lead through
  `processing → classified → proposal_ready` as the agent works.

### Technologies used

| Layer | Technology |
| --- | --- |
| Agent runtime | **Google ADK** (Agent Development Kit) 2.7.1 — Python, `LlmAgent` + `FunctionTool` |
| LLM | **Gemini API** — fast tier (`gemini-3.5-flash`) and brain tier for proposal writing |
| Frontend / API | **Next.js 15** (App Router, standalone output), React 19, TypeScript |
| Persistence | **SQLite** via `node:sqlite` (`DatabaseSync`) on the Node side, `sqlite3` on the Python side — no ORM |
| Auth | Node `crypto` scrypt + `timingSafeEqual`; Web Crypto HMAC-SHA256 sessions |
| Notifications | Telegram Bot API (stdlib `urllib` — no added dependency) |
| Deployment | Docker multi-stage (Node 22 + Python venv in one image), Traefik on VPS; Cloud Run ready |

### Data sources

- **Public lead intake form** — the primary source; name, email, service,
  budget, submitted by the client.
- **Telegram Bot API** — outbound notification channel.
- No third-party datasets. No scraped or purchased data. Nothing about a real
  person enters the repository: the database is gitignored and the committed
  seed script generates its own demo rows.

### Architecture summary

Two runtimes in one deployable unit. Next.js 15 serves the UI and API; a Python
ADK agent is spawned per lead by `POST /api/agent/process-lead`, which validates
the id, marks the lead `processing`, and returns 202 so the model work never
blocks a request. Both runtimes share one SQLite file and one audit trail. A
single Edge middleware gates every protected route.

Full diagram and data model: [`docs/architecture.md`](./architecture.md).

### Security

- Admin password compared with `timingSafeEqual` against a scrypt derivation —
  never `===`, and never stored in the database.
- Sessions are HMAC-SHA256 signed, httpOnly, SameSite=Lax, Secure in
  production, 24h expiry.
- Rate limiting: 5 login attempts / 60s and 10 lead submissions / 60s per IP.
- Fails closed — any missing auth variable and every protected route denies.
- Audit rows for logins, rejections, and every agent action. Passwords are
  never written to the log.

### Findings and learnings

The interesting problems were not the agent logic.

- **`gemini-3.5-pro` does not exist.** The model ids in the original plan were
  plausible and wrong. Verifying names against the live API before wiring them
  in — rather than trusting a spec — caught it. The brain-tier model also turned
  out to be quota-gated on a free key, so the config documents a flash fallback.
- **`.env` load order is a real bug surface.** A sub-agent module read
  `GEMINI_FAST_MODEL` at import time, which executed *before* `load_dotenv()` in
  the importing module — so the env value was silently ignored and the default
  used. Module-level env reads and dotenv loading do not compose.
- **Edge and Node crypto are not interchangeable.** Next.js middleware runs on
  the Edge runtime, where `node:crypto` does not exist. Webpack resolves `node:`
  schemes statically — even inside `await import()` — so a lazy import did not
  help and the build failed outright. The fix was an architectural split:
  Web Crypto HMAC for session verification (works in both runtimes), scrypt
  isolated in a module only the Node-pinned login route imports.
- **Next.js output-file-tracing swept the SQLite database into the build.**
  `.next/standalone/` contained `data/onboarding.db` — real lead data, one
  `COPY` away from being baked into a public image layer. Found by inspecting
  the build output rather than trusting it. Fixed in the Dockerfile
  unconditionally instead of relying on `.dockerignore` staying correct.
- **A rate limiter's honest scope matters.** The in-memory limiter keeps
  separate counters per runtime and per instance. It blunts brute-force from one
  client; it is not a distributed quota, and documenting that is more useful
  than implying a guarantee it cannot make.

---

## Testing instructions for judges

```
Live demo: https://onboarding.aiinvention.tech

1. Open the landing page and submit a lead on the public form
   (any name / email / service / budget). No login needed.

2. Watch it process live — the form polls the lead through
   processing → classified → proposal_ready as the agent runs.

3. Sign in to see the agent's work:
     URL:      https://onboarding.aiinvention.tech/login
     Password: Onboard@2026

4. On the dashboard, check:
   - Leads — your lead with its hot/warm/cold priority
   - Proposals — the overview / scope / timeline / pricing Gemini wrote
     (hover a section tag to read the full text)
   - Delivery Plans — discovery → build → review → handover
   - Audit Log — every step the agent took, including your login

To run it locally instead, the README has full setup. The test suite and a
dry-run of the agent both work with no API key:
   python -m agent.test_agent
   python -m agent.agent --lead '{"name":"Test","email":"t@example.com","service":"AI Website","budget":5000}' --dry-run
```

## Built with

```
google-adk, gemini-api, python, nextjs, react, typescript, sqlite, docker, traefik, google-cloud-run
```

---

## Prior work / reuse disclosure

```
Built new during the submission period (Aug 3–31, 2026). The repository's first
commit and all subsequent work fall inside that window.

Reused: the author's own internal patterns from previous AI Invention projects —
lead intake validation, the admin dashboard layout, and SQLite pipeline
conventions. These are the author's own prior art, re-implemented here rather
than copied wholesale.

No third-party code was incorporated beyond the declared open-source
dependencies in requirements.txt and package.json.

AI tooling: Claude Code was used as an AI coding assistant during development.
All architecture decisions, model placement, and security design were directed
and reviewed by the author.
```
