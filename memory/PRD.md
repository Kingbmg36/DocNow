# DocNow.NG — Product Requirements Document

**Status**: MVP shipped (Feb 2026)

## Original Problem Statement
Build a production-ready, mobile-first, AI-assisted healthcare platform for Africa (Nigeria first). The platform connects patients to verified doctors via AI-assisted triage, structured care plans, prescriptions, and health-vitals tracking. Roles: Patient, Doctor, Admin. NOT a hospital management or diagnostic tool.

## Architecture (adapted to Emergent platform)
- **Backend**: FastAPI (Python) + MongoDB (Motor async). Single `/app/backend/server.py` mounts modular routers under `/api/*`.
- **Frontend**: React 19 + Tailwind + Shadcn UI + Recharts + lucide-react. Fonts: Fraunces (headings) + DM Sans (body).
- **AI**: Anthropic Claude via the official `anthropic` SDK (`ai_service.py`), model env-configurable (`ANTHROPIC_MODEL`, default `claude-opus-4-8`). Powers triage, care plan, health tips. All AI calls have safe fallbacks if the model fails. *(Migrated off the Emergent Universal LLM Key / `emergentintegrations` for off-platform deploy — 2026-07.)*

> **Deployment (off Emergent):** de-Emergent-ized and containerised for **Railway** — Dockerfiles for both services, MongoDB Atlas for data, `requirements.txt` trimmed 127→18 (Emergent-base cruft removed; original at `backend/requirements-emergent-full.txt.bak`), `@emergentbase/visual-edits` removed from the frontend, `SEED_WIPE` now defaults `false` (was `true` — wiped the DB on every boot). CI (`.github/workflows/ci.yml`) runs backend pytest against a real Mongo service + frontend build on every push/PR, and deploys to Railway via CLI on `main` when service tokens are configured (`railway.json` in each service dir). Full runbook: `DEPLOY.md`.
> **Patient OTP delivery:** `otp.py` now fans out to `sms_service.py` (Termii SMS, primary — reaches any number, no opt-in) alongside the existing WhatsApp channel; either failing never blocks issuance. Fixed: the raw OTP code was being logged unconditionally — now only under `DEV_OTP_REVEAL=true`.
- **Auth**: JWT (httpOnly cookies + Bearer fallback) with bcrypt. RBAC: `patient`, `doctor` (status: pending/approved/suspended), `admin`. `require_approved_doctor` blocks pending doctors from clinical routes.
- **Payments**: Mocked Paystack (initialize + verify endpoints) — clean abstraction so real keys plug in by swapping `routes/payments.py`. Revenue split 70% doctor / 30% platform tracked on every payment.
- **Compliance**: NDPA-aligned, audit logging on every sensitive action, MongoDB indexes for users.email (unique), TTL for password reset tokens.

## User Personas
1. **Patient (e.g., Chioma in Lagos)** — needs quick, trustworthy care access without travelling.
2. **Doctor (e.g., Dr. Adaeze)** — practices remotely, picks cases from a triaged queue, earns 70% per consult.
3. **Admin (DocNow.NG staff)** — verifies doctors, monitors quality, sees platform health.

## What's Implemented (Feb 2026)
### WhatsApp Cloud API integration + rebrand to DocNow.NG (Iteration 8, Feb 2026)
- **Rebrand**: Medinest → DocNow.NG across all UI, page titles, copy, AI prompts, seed emails (`admin@docnow.ng`, `doctor@docnow.ng`), room ID prefix. Zero `Medinest` references outside historical test reports.
- **WhatsApp service** (`/app/backend/whatsapp_service.py`): stub/live dual-mode. Stub persists to `whatsapp_messages` with status='stubbed'; live POSTs to Meta Graph API with bearer token, retries on 5xx, idempotency via Mongo. Phone normalisation (E.164 → digits). 6 use-case helpers: OTP, appointment confirm/reminder, care plan, questionnaire link, weekly health tip.
- **WhatsApp routes** (`/app/backend/routes/whatsapp.py`): GET webhook verification (hub.challenge), POST webhook with HMAC-SHA256 signature verification (skipped only when APP_SECRET unset in dev), inbound message linking to existing patient by phone, STOP opt-out flow, doctor `/conversations/:patient_id` read+reply, admin `/status` + `/broadcast/health-tip` + `/broadcasts` history.
- **Scheduler** (`/app/backend/whatsapp_scheduler.py`): APScheduler cron job (Monday 09:00 Lagos) for weekly health-tip broadcast. Eligibility filter: role=patient, status≠deleted, phone set, `whatsapp_marketing_opt_in: True`, no tip in last 6 days. Off by default (`WHATSAPP_SCHEDULER_ENABLED=false`) to avoid surprise sends in dev.
- **Wired triggers**: OTP send (`otp.py`) → WhatsApp OTP template; appointment book (`routes/appointments.py`) → confirmation template; consultation complete (`routes/consultations.py`) → care plan + Rx code template.
- **Frontend WhatsApp UI**:
  - `WhatsAppChatPanel.jsx` — doctor-facing slide-in panel mounted in ConsultationRoom. 5s polling, status icons (sent/delivered/read/failed), template tags on outbound, 24h care-window hint.
  - AdminDashboard "WhatsApp" tab — integration health card (mode badge live/stub, message counts), broadcast card (AI-generated or custom tip), history list with eligible/sent/failed counts.
- **Auto-opt-in mirror**: `wants_health_tips` answer in patient_intake auto-sets `whatsapp_marketing_opt_in` on the user doc.
- **Tests** (`/app/backend/tests/test_whatsapp.py`): 20 tests, 3.65s, all pass. Covers stub persistence, idempotency, summary truncation, HMAC verify (3 cases), webhook GET/POST, inbound patient-linking, STOP opt-out, admin status + broadcast RBAC, doctor conversation RBAC, scheduler opt-out exclusion, 6-day cooldown.

### Nigeria-focused 7-section patient intake questionnaire (Iteration 7, Feb 2026)
- **patient_intake schema v2** (`/app/backend/questionnaire_service.py`) — 7 sections, 51 fields covering Section 2 enrichment (LGA, occupation, marital, next-of-kin), General health & medical history (overall health, BP status, expanded chronic list, surgeries, malaria last 12mo, sickness frequency, drug reactions), Immunizations (childhood, yellow fever, hep B, COVID, tetanus), Lifestyle, Mental wellbeing (PHQ-2/GAD-2), Healthcare access/goals/consent (insurance, hospital type, communication channel, AI consent), and Family health.
- **Auto-mirror to user profile**: 50+ keys mirror onto `users` doc on submit; `past_illnesses` auto-merges into `chronic_conditions` via mapping → derived signals (`risk_score`, `care_segment`) recompute.
- **PatientDashboard wiring**: intake modal auto-opens on first dashboard visit (localStorage `mdn_intake_dismissed_<userId>` gate); intake banner CTA on overview re-opens it.
- **DoctorDashboard wiring**: doctor_onboarding auto-opens on first visit until completed; doctor_refresh banner appears when 180-day refresh is due.
- **ConsultationRoom wiring**: on doctor "Complete consultation", non-dismissible doctor_post_consult modal opens; on submit, doctor navigates back to /doctor.

### Phone-OTP onboarding + 4-gate progressive profile (Iteration 4-5, Jun 2026)
- **Gate 1** (60-sec signup): phone OTP (mock provider, Termii-ready) + name + DOB + gender + state + language + granular consent (care delivery required, analytics / model training / research opt-in)
- **Gate 2** (clinical safety floor — triggered at first "Start Consultation"): genotype, blood group, height, weight, chronic conditions, current meds, allergies, emergency contact, **Section 14 red-flag screen** (10 emergency signs)
- **Versioned profile**: `users` (snapshot, mutable) + `profile_events` (append-only history per field change) + `derived_signals` (recomputed `risk_score` 0-100, `triage_priority` Emergency/High/Moderate/Low, `care_segment` like "hypertensive,maternal,senior", `next_best_actions[]`)
- **Profile completeness ring** on patient Overview with Gate-1 / Gate-2 progress + next-best-action card
- Patient creation gated: `POST /cases` returns 412 until Gate 2 done
- Admin/doctor still use email/password (operational)
- Backend bugs fixed: partial unique index on `email`, no leak of `_id`, lazy `recompute_signals` on `/profile/me`

### Backend modules
- `auth` — register / login (brute-force lockout) / me / logout / refresh / forgot-password (token to logs) / reset-password / admin + demo seeding
- `patients` — profile CRUD
- `doctors` — profile CRUD + public approved-doctor listing
- `triage` — GPT-5.2 structured JSON output (urgency, red_flags, specialty, next_steps, doctor_questions, disclaimer)
- `cases` — patient creates with triage, doctor queue (sorted by urgency), assigned cases, single-case detail with RBAC
- `consultations` — accept (atomic case status transition), chat messages, doctor notes, prescription create/update, complete → auto care plan via AI + 70% doctor earnings credit
- `prescriptions` & `care_plans` — read endpoints
- `vitals` — patient CRUD with type/value/unit/note
- `payments` — mock Paystack init/verify, moves case `pending_payment` → `queued`
- `feedback` — rating 1-5, updates doctor `rating_avg`/`rating_count`
- `admin` — users, pending doctors, approve/reject/suspend/reinstate, all consultations, all payments, audit logs, analytics
- `health_tips` — AI-generated 5-category daily tips with fallback

### Frontend
- **Landing**: hero with Nigerian doctor imagery, stats strip, how-it-works, for-doctors block, trust/safety, CTA
- **Auth**: Login (split-screen with safety note), Register (role selector + role-specific fields)
- **Patient Dashboard** (`/patient`): Overview, Start Consultation wizard (Symptoms → AI Triage → Mock Payment → Done), History, Care Plans (with structured sections + feedback form), Prescriptions (Rx code receipt cards), Vitals (Recharts line charts + add form), Health Tips
- **Doctor Dashboard** (`/doctor`): Pending-status banner OR Overview, Queue (urgency-sorted, Accept button), My active cases, History, Prescriptions issued, Earnings, Ratings
- **Admin Dashboard** (`/admin`): Overview tiles, Users table with role filter, Doctor Approvals, Consultations, Payments, Analytics, Feedback
- **Consultation Room** (`/consultation/:id`): Chat (5s polling), AI triage card, doctor notes + prescription form + complete CTA, read-only prescription & care plan after completion
- **Safety**: emergency banner on every dashboard footer; disclaimers on triage and tips

## Test Coverage
- Backend: 42/42 pytest cases (auth, RBAC, triage AI, cases, payments, consultations, prescriptions, care plans, vitals, feedback, admin, analytics)
- Frontend: 14/14 critical e2e flows via Playwright (landing, login, all 7 patient tabs, full consultation flow with real GPT-5.2 triage, doctor accept→chat→complete with care plan, admin approve, RBAC redirect)

## Seeded Test Credentials
See `/app/memory/test_credentials.md`. Admin / approved doctor / pending doctor / patient.

## Backlog (Prioritized)

### P0 (next iteration)
- ✅ **Real Paystack integration (done)** — `paystack_service.py` stub/live dual-mode; `routes/payments.py` does live `initialize` (hosted checkout) + `verify` + a signature-verified `/api/payments/webhook` (`charge.success`). Shared idempotent `_fulfil_payment` (amount-tampering guard, atomic case advance). Frontend redirects to Paystack in live mode and confirms on return; stub flow preserved for keyless dev. Config: `PAYSTACK_ENABLED` + `PAYSTACK_SECRET_KEY`. Tests: `tests/test_payments.py`.
- ✅ **Email integration (done)** — `email_service.py` stub/live dual-mode (Resend). Wired into `forgot-password` (real reset link; token only logged in dev) and consultation completion (care-plan email alongside WhatsApp). Idempotent, persists to `emails`. Config: `EMAIL_ENABLED` + `RESEND_API_KEY` + `EMAIL_FROM`. Tests: `tests/test_email.py`.
- ✅ **Doctor license document upload (done)** — `storage_service.py` pluggable local/S3 backend (boto3 lazy; access always streamed through an authorised API route, never a public URL). `POST /doctors/license` (PDF/JPG/PNG ≤10 MB → `license_document` on the user), `GET /doctors/{id}/license/file` (doctor-own or admin). Admin decision marks the doc verified/rejected. Frontend: doctor uploads from the pending banner; admin views it on the approval card. Config: `STORAGE_BACKEND` (local|s3). Tests: `tests/test_storage.py`.

### P1
- Patient profile edit screen (backend ready, UI not exposed in tabs)
- Doctor profile edit screen (backend ready, UI not exposed in tabs)
- Push notifications for "doctor accepted your case"
- Health Tips personalisation by patient conditions

### P2 (future-ready architecture in place)
- Wearable integrations (Apple Health, Google Fit) — vitals model supports this
- Pharmacy/lab integrations
- Multi-country, multilingual (i18n)
- AI voice consultations
- Medication delivery

## Architectural Decisions
- **MongoDB over Postgres** (Emergent environment standard) — schemas modeled as documents with proper indexes.
- **Bearer token primary** on frontend (cookies still set as defense-in-depth) — avoids CORS-with-credentials complexity when frontend/backend may be on different preview domains.
- **AI safety**: every AI endpoint has a try/except with deterministic fallback so the platform never blocks on AI failure.
- **PRBAC depth**: `require_approved_doctor` is a separate dependency only on clinical routes; pending doctors retain self-profile access.

## Compliance Notes
- All actions audited to `audit_logs` collection
- Passwords bcrypt-hashed with random salt per user
- Brute-force lockout (5 attempts / 15 min window)
- Sensitive fields stripped from API responses (`password_hash`, `_id`)
- Reset tokens single-use + 1h TTL
- Mandatory medical disclaimer in every triage and care plan output
