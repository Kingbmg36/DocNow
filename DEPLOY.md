# Deploying DocNow.NG to Railway

This app is now Emergent-free and container-ready: a **FastAPI backend** and a
**React (CRA/CRACO) frontend**, each with a Dockerfile, plus **MongoDB Atlas** for data
and **Anthropic Claude** for AI. Two Railway services + one Atlas cluster.

```
┌─ Railway project ──────────────────────────────┐
│  backend  (Dockerfile, FastAPI)  ── MONGO_URL ──┼──▶ MongoDB Atlas (M0 free)
│  frontend (Dockerfile, static)   ── REACT_APP_BACKEND_URL ─▶ backend
└─────────────────────────────────────────────────┘
```

## 0. Accounts & keys you'll need

- GitHub repo containing this code
- [Railway](https://railway.app) account
- [MongoDB Atlas](https://www.mongodb.com/atlas) account (free M0 tier is fine to start)
- **Anthropic API key** (`sk-ant-…`) from console.anthropic.com
- **Paystack** secret + public keys (`sk_test_…` / `pk_test_…` work end-to-end in test mode)
- *(optional)* Resend API key for email; Meta WhatsApp credentials for WhatsApp/OTP delivery

---

## 1. MongoDB Atlas

1. Create a free **M0 cluster**.
2. **Database Access** → add a user (username + password). Save them.
3. **Network Access** → add `0.0.0.0/0` (allow from anywhere — Railway egress IPs aren't static on the free tier).
4. **Connect → Drivers** → copy the connection string, e.g.
   `mongodb+srv://USER:PASSWORD@cluster0.xxxx.mongodb.net/?retryWrites=true&w=majority`
   This is your `MONGO_URL`.

---

## 2. Push to GitHub

Commit and push this directory. Confirm `.env` is **not** committed (the root `.gitignore`
now ignores it). `.env.example` files *are* committed — that's intended.

---

## 3. Backend service (deploy first — the frontend needs its URL)

1. Railway → **New Project → Deploy from GitHub repo**.
2. Add a service, set **Root Directory = `backend`**. Railway auto-detects `backend/Dockerfile`.
3. Add the variables below (**Variables** tab). Do **not** set `PORT` — Railway injects it.
4. **Settings → Networking → Generate Domain**. That's your backend URL (e.g. `https://docnow-backend.up.railway.app`).

**Backend variables**

| Variable | Value / notes |
|---|---|
| `MONGO_URL` | Atlas connection string from step 1 |
| `DB_NAME` | `docnow` |
| `JWT_SECRET` | long random string — generate with `openssl rand -hex 32` |
| `ADMIN_EMAIL` | your admin login email |
| `ADMIN_PASSWORD` | a strong admin password |
| `SEED_WIPE` | `false` ← **never `true` in prod** (it wipes all collections on boot) |
| `DEV_OTP_REVEAL` | `false` in prod (dev-only convenience that returns OTP codes in the API) |
| `FRONTEND_URL` | set after step 4 to the **frontend** URL (used for reset links, care-plan email links, Paystack callback) |
| `ANTHROPIC_API_KEY` | `sk-ant-…` |
| `ANTHROPIC_MODEL` | `claude-opus-4-8` (default) — or `claude-sonnet-5` to cut AI cost |
| `PAYSTACK_ENABLED` | `true` to take real payments |
| `PAYSTACK_SECRET_KEY` | `sk_test_…` / `sk_live_…` |
| `PAYSTACK_PUBLIC_KEY` | `pk_test_…` / `pk_live_…` |
| `EMAIL_ENABLED` | `true` + `RESEND_API_KEY` to send email; else stub (logged) |
| `RESEND_API_KEY`, `EMAIL_FROM` | if `EMAIL_ENABLED=true` |
| `STORAGE_BACKEND` | `local` (default) or `s3` + `STORAGE_S3_BUCKET` + `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` |
| `SMS_ENABLED` | `true` + `TERMII_API_KEY` + `TERMII_SENDER_ID` to send real patient-OTP SMS (primary OTP channel — see termii.com) |
| `WHATSAPP_ENABLED` | `false` until Meta Cloud API is configured (see `backend/.env.example`) — secondary OTP channel |

> Full list with comments: `backend/.env.example`.

---

## 4. Frontend service

1. In the same project, add another service from the same repo, **Root Directory = `frontend`**.
2. Add the variable below. It's baked in at **build time**, so it must be set before the first build.

| Variable | Value |
|---|---|
| `REACT_APP_BACKEND_URL` | the backend URL from step 3 (no trailing slash) |

3. **Generate Domain** for the frontend.
4. Go back to the **backend** service and set `FRONTEND_URL` to this frontend URL, then redeploy the backend (quick).

> Changing `REACT_APP_BACKEND_URL` later requires a **frontend rebuild** (CRA bakes it in) — redeploy the frontend service.

---

## 5. Paystack webhook

In the Paystack dashboard → **Settings → API Keys & Webhooks**, set the webhook URL to:

```
https://<your-backend-domain>/api/payments/webhook
```

This is the authoritative payment-fulfilment path (HMAC-SHA512 verified). Without it, payments
only confirm via the browser return.

---

## 6. First boot & smoke test

On first backend deploy, `seed_admin_and_demo()` creates the admin (and demo doctor/patient) —
it does **not** wipe because `SEED_WIPE=false`.

1. `GET https://<backend>/api/health` → `{"status":"healthy"}`
2. Open the frontend URL → log in as admin (`ADMIN_EMAIL` / `ADMIN_PASSWORD`).
3. Register a doctor, upload a license (Doctor dashboard), approve it (Admin dashboard).
4. As a patient, run the symptom checker (exercises Claude) and book → pay (Paystack test card).

Run the backend test suite on the platform if you like:
`cd backend && pip install -r requirements-dev.txt && python -m pytest tests/ -v` (needs `MONGO_URL`/`DB_NAME` set). `requirements-dev.txt` layers pytest on top of the production `requirements.txt` — it's intentionally not installed in the Docker image.

---

---

## CI / one-push deploys (`.github/workflows/ci.yml`)

Every push and PR: runs the backend pytest suite against a real Mongo service container
(boots `uvicorn`, waits for `/api/health`, then runs `pytest tests/ -v`), and builds the
frontend (`yarn build`) to catch build breaks. On a push to `main`, a `deploy` job runs
after both pass.

**To enable the deploy job** (optional — see the alternative below):

1. Railway → **backend service → Settings → Tokens** → create a service token. Add it to
   the GitHub repo as secret **`RAILWAY_TOKEN_BACKEND`** (Settings → Secrets and variables → Actions).
2. Repeat for the **frontend service** → secret **`RAILWAY_TOKEN_FRONTEND`**.
3. That's it — pushes to `main` that pass tests now deploy both services via `railway up`.

**Without those secrets**, the deploy job no-ops (logs a message and exits 0) — tests still
gate the build either way. If you'd rather not use GitHub Actions for deploy at all, connect
the GitHub repo directly in the Railway dashboard (**Settings → Source**) and Railway's own
integration auto-deploys on push; the CI workflow's `backend-test`/`frontend-build` jobs still
run and report status, they just won't be the thing triggering the deploy.

> **Not run in this session** — building the workflow needed Docker + MongoDB, neither
> available in the sandbox that produced it. The YAML is syntax-validated; the actual
> pytest run against a live Mongo will be its first real execution, on your first push.

---

## Known gaps to close before real launch

- **Patient OTP delivery — now wired (SMS primary, WhatsApp secondary).** `send_otp()` fans out
  to both `sms_service.py` (Termii — reaches any Nigerian number, no opt-in required) and the
  existing WhatsApp channel; either failing never blocks issuance. Both default to stub/logged
  until `SMS_ENABLED=true` + `TERMII_API_KEY`, and `WHATSAPP_ENABLED=true` + Meta creds + approved
  templates, respectively. **Security fix included:** the raw OTP code is no longer logged
  unconditionally — only when `DEV_OTP_REVEAL=true` (keep that `false` in production).
- **Dependency slimming (done):** `requirements.txt` was trimmed from the 127-line Emergent base to the
  ~20 packages the app imports. The original is kept at `backend/requirements-emergent-full.txt.bak`.
- **`yarn.lock`:** regenerate locally (`cd frontend && yarn install`) after the `@emergentbase` removal for
  a fully pinned build; the Dockerfile tolerates the stale lock in the meantime.
- **CORS** is currently `*` (fine with Bearer-token auth). Lock to your frontend origin if you add
  cookie-based cross-site flows.
