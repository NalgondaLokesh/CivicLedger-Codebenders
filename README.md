# CivicLedger: Claim What's Yours

CivicLedger (Problem Statement 5: Claim What's Yours) is an indicative
scheme-eligibility assistant for Telangana. It helps students discover
scholarships, fee reimbursements, and overseas-study support, with an
AI-assisted eligibility check and an application tracker.

All eligibility shown is **indicative only** ("Likely Eligible" / "Needs
Clarification" / "Not Likely"), never guaranteed. No Aadhaar, PAN, or other
sensitive IDs are collected, stored, or displayed.

## Problem

Many eligible students, small farmers, and women entrepreneurs in Telangana
do not claim the state and central welfare schemes they qualify for. Scheme
rules are spread across portals, the criteria are hard to compare, and it is
unclear which documents are needed. (Hackathon problem statement PS 5: "Claim
What's Yours".)

## Solution

CivicLedger is an indicative eligibility and application-tracking assistant.
A user describes their situation in plain language, or fills in a criteria
filter. The system returns matching schemes marked "Likely Eligible",
"Needs Clarification", or "Not Likely", explains which rule matched, lists
required documents and application steps, and links the official portal with
a last-verified date. Users can save schemes to a tracker, tick off documents,
and set reminders.

Rules are deterministic and stored as data in MongoDB Atlas. Qdrant Cloud
retrieval supplies grounded context. Groq extracts attributes from free text,
with a keyword fallback when Groq is not configured.

## Who it is for

- Students seeking post-matric, professional, or overseas scholarships.
- Small farmers.
- Women entrepreneurs.

These match the three persona cards on the landing page. The app is also
meant for citizens who want a quick, no-login first check.

## How it works

1. The user enters a story or sets filters.
2. Aadhaar- and PAN-like numbers are masked before processing.
3. Traits are extracted: education level, category, annual income, state, and
   overseas need.
4. If key fields are missing, the assistant asks up to two follow-up rounds,
   or shows matches when the user requests them.
5. Deterministic rule checks run against scheme records in MongoDB, with Qdrant
   snippets as context.
6. Each result shows the matched rules, documents, steps, `official_url`, and
   `last_verified_date`.
7. The user can save a scheme to the tracker.

## Who operates it

- Scheme data: whoever maintains the `schemes` collection in MongoDB Atlas.
  Edit rules there, then re-run the Qdrant sync so search reflects the change.
- Deployment: the team running the FastAPI backend and the Vite frontend
  locally or on their own hosting. No Docker is used.
- Credentials: MongoDB, Qdrant, and Groq keys are held by the operator in
  `backend/.env`, never committed.
- Verification of scheme facts: the operator must re-check each `official_url`
  and update `last_verified_date` when rules change.

Operator roles should be confirmed by the project team.

## Limitations

- Results are indicative, not legal determinations.
- Auth is a local placeholder. There are no server-side accounts yet.
- Embeddings are deterministic hashing vectors, not a learned model.
- Live verification against MongoDB Atlas, Qdrant Cloud, and Groq is not yet
  complete.
- Scheme coverage is limited to the seeded records.


## Stack

- `backend/`: Python + FastAPI, MongoDB (Atlas), Qdrant Cloud (vector
  retrieval), Groq API (trait extraction)
- `frontend/`: React 18 + Vite, mobile-first responsive UI
- No Docker. Everything runs directly on the host.

## Features

- **Scheme Explorer**: lists schemes from `GET /api/schemes`.
- **AI Eligibility Check**: `POST /api/eligibility/chat`. Aadhaar- and
  PAN-like numbers are masked before processing. Statuses are "Likely
  Eligible", "Needs Clarification", and "Not Likely". Traits are extracted
  with Groq, with a keyword fallback. Qdrant retrieval supplies context
  snippets.
- **Application Tracker**: `/api/tracker` endpoints for list, create, patch,
  delete, checklist, and checklist toggle. Reminder states are "Overdue",
  "Due soon", and "Scheduled". Notes are sanitised for ID numbers.
- **Landing page** and **AuthPanel** (local placeholder session, with Guest
  mode).
- **Warm Civic design theme**: `frontend/src/styles/theme.css`.
- **Logo**: `frontend/public/CivicLedger_Logo.jpg`, used in the header, the
  landing hero, and the favicon.

## Prerequisites

- Python 3.10+ and Node.js 18+
- Credentials in `backend/.env`. Copy `backend/.env.example` to
  `backend/.env` manually and fill in real values. Never commit secrets.
  - `MONGODB_URI`, `MONGODB_DB_NAME`: MongoDB Atlas
  - `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`: Qdrant Cloud
  - `GROQ_API_KEY`, `GROQ_MODEL`: Groq API
  - All cloud variables are optional. The app still starts and degrades
    gracefully (keyword fallback extraction, no RAG snippets) without them.
- Frontend: `VITE_API_BASE` sets the API base URL. It defaults to
  `http://localhost:8000` if unset.

## Setup and run (Windows, from repo root)

### 1. Backend

```powershell
cd backend
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe seed_schemes.py
.venv\Scripts\python.exe -m app.sync_qdrant
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

- `seed_schemes.py` is idempotent and safe to rerun.
- `app.sync_qdrant` is idempotent. It creates the Qdrant collection and
  payload indexes on first run.
- API docs: http://localhost:8000/docs

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```

- Vite dev server: http://localhost:5173
- Production build: `npm run build`

## Live verification checklist

Run these to confirm cloud connectivity end-to-end:

| Check | Command | Expected |
|---|---|---|
| Health | `curl http://localhost:8000/api/health` | `mongodb: up`, `qdrant: up`, `groq: configured` |
| Schemes | `curl "http://localhost:8000/api/schemes?category=ebc"` | JSON list of matching schemes |
| Seed | `.venv\Scripts\python.exe seed_schemes.py` | `Seeded 0 new, 7 updated` on rerun |
| Qdrant sync | `.venv\Scripts\python.exe -m app.sync_qdrant` | `Schemes: 7`, `Chunks: 35`, `Upserted: 35` |
| Eligibility | `POST /api/eligibility/chat` with a plain-language story | traits extracted, `pii_warning` if IDs present, rule-backed matches |
| Tracker | `POST /api/tracker` → checklist → toggle → PATCH → DELETE | 201 / 409 duplicate / 404 missing; checklist progress updates |

## Demo walkthrough

0. **Open the app**: go to http://localhost:5173 and either continue as Guest
   or use the local placeholder session in AuthPanel. Landing is the
   pre-login page.
1. **Scheme Explorer**: filter by education level, category, or income. Point
   out the trust banner, the "Likely Eligible" tags, the `last_verified_date`
   badges, and the official portal links.
2. **AI Check**: send a sample story (or type one, e.g. "SC student in
   Warangal, post matric, income 1 lakh"). Show trait chips, follow-up
   questions, match cards with rule reasons, and the PII-masking banner (try
   including a fake 12-digit number).
3. **Tracker**: click "Save & Track" on a match, switch to the Tracker tab,
   tick documents in the checklist, set a reminder date, and move the status
   through Documents Pending, Ready to Apply, and Applied.

## API endpoints

- `GET /api/health`: mongodb / qdrant / groq status
- `GET /api/schemes`: scheme list, with filters `education_level`,
  `category`, `max_income`
- `POST /api/eligibility/chat`: conversational eligibility (PII-masked)
- `GET /api/tracker`, `POST /api/tracker`: list and create saved schemes
- `PATCH /api/tracker/{item_id}`, `DELETE /api/tracker/{item_id}`: update and
  delete saved schemes
- `GET /api/tracker/checklist`: document checklist
- `POST /api/tracker/checklist/toggle`: toggle a checklist item

## Privacy guardrails

- No Aadhaar, PAN, or other sensitive IDs are collected or stored.
- The `Scheme` schema intentionally has **no** fields for Aadhaar numbers or
  other sensitive identifiers. Chat messages and tracker notes are masked
  before storage.
- Eligibility is indicative only, never guaranteed.
- Every scheme shows its `official_url` and `last_verified_date`.
- Scheme rules are editable data in MongoDB Atlas (`schemes` collection),
  not hardcoded in the UI.

## Status

- The frontend build passes.
- The backend has been compiled and imported only in part.
- Live verification against MongoDB Atlas, Qdrant Cloud, and Groq has NOT
  been done yet.
- Not yet done: the Scheme Explorer criteria sidebar, the mobile drawer, and
  restyling of the AI and Tracker views.

## Built with

This project was built using the Codebenders IDE.

