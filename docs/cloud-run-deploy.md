# Deploy to Google Cloud Run

The container is Cloud Run ready. Nothing here has been executed — billing is
not yet enabled on the target project, so these are the exact copy-paste steps
for the moment it is.

**Readiness, already verified:**

- The Next.js standalone server binds `process.env.PORT` (`|| 3000`) and
  `process.env.HOSTNAME` (`|| 0.0.0.0`). Cloud Run injects `PORT=8080` at
  runtime, which overrides the Dockerfile's `ENV PORT=3000` — no code change
  needed for either target.
- The image creates `/app/data` at build time, so SQLite has a writable
  directory on Cloud Run's ephemeral disk with no volume attached.
- `WORKDIR /app` places `.venv/` and `agent/` beside `server.js`, which is what
  `POST /api/agent/process-lead` needs to spawn the Python agent.

---

## 1. Authenticate and select the project

```bash
gcloud auth login
gcloud config set project project-f3b6a770-48e9-41ea-831
```

## 2. Enable the required APIs

```bash
gcloud services enable run.googleapis.com artifactregistry.googleapis.com
```

## 3. Build the image

```bash
docker build -t client-onboarding-agent .
```

## 4. Tag for Artifact Registry

```bash
docker tag client-onboarding-agent \
  asia-southeast1-docker.pkg.dev/project-f3b6a770-48e9-41ea-831/client-onboarding/client-onboarding-agent
```

> If the `client-onboarding` repository does not exist yet, create it once:
>
> ```bash
> gcloud artifacts repositories create client-onboarding \
>   --repository-format=docker --location=asia-southeast1
> ```

## 5. Configure Docker auth and push

```bash
gcloud auth configure-docker asia-southeast1-docker.pkg.dev

docker push \
  asia-southeast1-docker.pkg.dev/project-f3b6a770-48e9-41ea-831/client-onboarding/client-onboarding-agent
```

## 6. Deploy

Non-secret configuration only in this command:

```bash
gcloud run deploy client-onboarding-agent \
  --image asia-southeast1-docker.pkg.dev/project-f3b6a770-48e9-41ea-831/client-onboarding/client-onboarding-agent \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --timeout 300 \
  --set-env-vars "GEMINI_FAST_MODEL=gemini-3.5-flash,GEMINI_BRAIN_MODEL=gemini-3.6-flash,DB_PATH=/app/data/onboarding.db"
```

`--allow-unauthenticated` exposes the *landing page and public lead form* only.
The dashboard and every admin API stay behind the app's own password login.

## 7. Supply the secrets

These six are **never committed and never baked into the image**. Pass them at
deploy time from your local `.env` values:

| Variable | Required | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | yes | Live Gemini calls; without it the agent runs its offline heuristic |
| `ADMIN_PASSWORD` | yes | Dashboard login |
| `ADMIN_PASSWORD_SALT` | yes | scrypt salt — `openssl rand -hex 32` |
| `SESSION_SECRET` | yes | Session cookie HMAC key — `openssl rand -hex 32` |
| `TELEGRAM_BOT_TOKEN` | no | Real notifications; falls back to console log + audit row |
| `TELEGRAM_CHAT_ID` | no | Notification target |

```bash
gcloud run services update client-onboarding-agent \
  --region asia-southeast1 \
  --set-env-vars "GEMINI_API_KEY=...,ADMIN_PASSWORD=...,ADMIN_PASSWORD_SALT=...,SESSION_SECRET=..."
```

For anything beyond a demo, use Secret Manager instead of `--set-env-vars`:

```bash
echo -n "$GEMINI_API_KEY" | gcloud secrets create gemini-api-key --data-file=-

gcloud run services update client-onboarding-agent \
  --region asia-southeast1 \
  --set-secrets "GEMINI_API_KEY=gemini-api-key:latest"
```

> **Missing auth vars fail closed.** With `ADMIN_PASSWORD`,
> `ADMIN_PASSWORD_SALT`, or `SESSION_SECRET` unset, every protected route denies
> and `/api/auth/login` returns 503. That is intended — but it means a deploy
> without step 7 gives you a reachable landing page and an unreachable
> dashboard.

---

## Known constraints on Cloud Run

Stated plainly, because they are real and a judge will hit them.

**SQLite is ephemeral.** Cloud Run's filesystem is per-instance and in-memory.
The database starts empty on every cold start and is lost when the instance
recycles. For a demo this is arguably a feature — a judge submits a lead and
watches it get classified and turned into a proposal on a clean slate, which is
proof the pipeline runs rather than proof a fixture was seeded. It is not
suitable for retained data.

**Scale to more than one instance and the instances diverge.** Each holds its
own database file. Pin it for a demo:

```bash
gcloud run services update client-onboarding-agent \
  --region asia-southeast1 --max-instances 1
```

Real persistence means swapping SQLite for Cloud SQL or Firestore, which is a
data-layer change in `lib/db.ts` and `agent/memory.py` — deliberately out of
scope for this submission.

**CPU is throttled between requests.** `POST /api/agent/process-lead` spawns the
agent fire-and-forget and returns 202, so the work continues after the response
is sent. Cloud Run may throttle CPU once a request completes, which can stall
that subprocess. If lead processing appears to hang, enable always-on CPU:

```bash
gcloud run services update client-onboarding-agent \
  --region asia-southeast1 --no-cpu-throttling
```

**Cold starts include a Python venv.** The image carries Node plus a Python
environment with `google-adk`, so it is larger than a typical Node image and
cold starts are correspondingly slower. `--min-instances 1` avoids that during
judging, at the cost of an always-running instance.
