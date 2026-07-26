# DocNow.NG

AI-assisted telemedicine for Africa, starting with Nigeria. Patients get triaged
symptoms, book verified doctors, and receive prescriptions + care plans; doctors
manage a consultation queue and earn per visit; admins approve doctors and monitor
the platform.

- **Backend** — FastAPI + MongoDB (Motor), JWT auth, Anthropic Claude for triage/care
  plans. `backend/`
- **Frontend** — React 19 (CRA/CRACO) + Tailwind + shadcn/ui. `frontend/`
- **Product context** — `memory/PRD.md`

## Deploy

- **Render (recommended)** — `DEPLOY-RENDER.md`, config in `render.yaml`
- **Railway** — `DEPLOY.md`, config in `backend/railway.json` / `frontend/railway.json`

## Local development

See `backend/.env.example` and `frontend/.env` for required configuration.

```bash
cd backend && pip install -r requirements.txt && python server.py
cd frontend && yarn install && yarn start
```
