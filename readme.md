# Knowledge Transfer (KT) — EBC App Backend (Perenti Community API)

> **Service name:** `ebc-app-backend`  
> **Canonical repo path:** `community/website/ebc-app-backend`  
> **Stack:** Python 3.12 · FastAPI · Appwrite · Cloudinary · Render  
> **Last updated:** June 2026

---

## 1. What Is This Service?

This is the **sole backend API** for the Perenti (formerly "EBC") community platform. It powers:

| Feature | Description |
|---|---|
| Member Directory | Profiles of community members sourced from a Google Form CSV |
| Meetup Listings | Community meetups with capacity management |
| Reservations & Ticketing | Registration, payment-pending flows, QR-code tickets |
| Admin Approval | Admin can approve/reject pending reservations |
| Chat Messages | Basic DM-style messaging between members |
| Avatar Uploads | Image upload to Cloudinary with face-crop transformation |
| Authentication | Lightweight email-lookup-based auth (no real JWT) |

The service is a **single-file FastAPI app** (`main.py`) with ~960 lines — no microservice split, no routers, no separate packages.

---

## 2. Tech Stack & External Dependencies

| Layer | Technology | Notes |
|---|---|---|
| Language | Python 3.12 | Pinned in `render.yaml` |
| Web framework | **FastAPI** | Async-capable; CORS is fully open (`allow_origins=["*"]`) |
| ASGI server | **Uvicorn** | Started with `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Database / BaaS | **Appwrite** | Used as NoSQL document store; Python SDK v5+ |
| File / Image storage | **Cloudinary** | Avatar images only; stored in `ebc_avatars/` folder |
| Config management | **python-dotenv** | `.env` file locally; Render environment vars in production |
| Email (SMTP) | stdlib `smtplib` | Opt-in; falls back to stdout preview if SMTP creds absent |
| QR codes | External API | `https://api.qrserver.com/v1/create-qr-code/` (no key needed) |
| Data seeding | **Pandas** | Only used in `upload_data.py` for CSV-to-Appwrite migration |
| Deployment | **Render** | Configured via `render.yaml` |

---

## 3. Project File Map

```
ebc-app-backend/
├── main.py                  # ★ ENTIRE application — all routes, models, helpers
├── requirements.txt         # pip dependencies
├── render.yaml              # Render.com deployment config
├── .env                     # Local secrets (gitignored)
├── .gitignore               # Excludes venv/, .env, *.csv, *.log, __pycache__
│
├── seed_meetups.py          # One-time: create Appwrite collections + seed EBC 28th meetup
├── upload_data.py           # One-time: parse Google Form CSV → Appwrite profiles
├── schema_fetch.py          # Utility: fetch & print Appwrite collection schema
├── test_appwrite.py         # One-time: manually create attributes for 'messages' collection
│
├── test_api.py              # pytest-based API tests (uses FastAPI TestClient)
│
└── Ekthaa Community ...csv  # Source data for member profiles (gitignored in prod)
```

> **Rule of thumb:** Everything runtime-critical lives in `main.py`. The other `.py` files are one-off utilities or tests.

---

## 4. Environment Variables

All secrets live in `.env` (local) and Render env vars (production). **Never commit `.env`.**

| Variable | Purpose | Where Used |
|---|---|---|
| `APPWRITE_ENDPOINT` | Appwrite API base URL (e.g. `https://fra.cloud.appwrite.io/v1`) | `main.py`, `upload_data.py`, `seed_meetups.py` |
| `APPWRITE_PROJECT_ID` | Appwrite project identifier | All Appwrite calls |
| `APPWRITE_API_KEY` | Server-side API key (full DB access) | All Appwrite calls |
| `APPWRITE_DATABASE_ID` | Appwrite Database ID (value: `community_app_db`) | All DB queries |
| `APPWRITE_PROFILE_COLLECTION_ID` | Collection ID for member profiles | Member endpoints |
| `APPWRITE_MEETUPS_COLLECTION_ID` | Collection ID for meetups (default: `meetups`) | Meetup endpoints |
| `APPWRITE_RESERVATIONS_COLLECTION_ID` | Collection ID for reservations (default: `reservations`) | Reservation endpoints |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary account cloud name | Avatar upload |
| `CLOUDINARY_API_KEY` | Cloudinary API key | Avatar upload |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret | Avatar upload |
| `SMTP_HOST` | SMTP server hostname | Ticket email sending |
| `SMTP_PORT` | SMTP port (default `587`) | Ticket email sending |
| `SMTP_USER` | SMTP login / From address | Ticket email sending |
| `SMTP_PASSWORD` | SMTP password | Ticket email sending |

> If `SMTP_HOST`, `SMTP_USER`, or `SMTP_PASSWORD` are missing, the email function silently logs to stdout and returns `False` — the reservation still succeeds.

---

## 5. Appwrite Database Schema

Database ID: **`community_app_db`**

### 5.1 Collection: `profiles` (ID from `APPWRITE_PROFILE_COLLECTION_ID`)

Holds member profile data originally seeded from the Google Form CSV.

| Attribute | Type | Max Size | Notes |
|---|---|---|---|
| `user_id` | string | — | UUID hex, generated at insertion |
| `name` | string | 255 | Display name |
| `full_name` | string | 255 | Duplicates `name` |
| `role` | string | 255 | Duplicates `profession` |
| `profession` | string | 255 | Member's stated profession |
| `area` | string | 255 | City / location |
| `bio` | string | 2000 | Auto-generated from form answers |
| `whyJoined` | string | 2000 | Collaboration intent |
| `whatTheyExpect` | string | 2000 | Collaboration preference |
| `howTheyCanHelp` | string | 2000 | Skills offered |
| `linkedIn` | string | 1000 | LinkedIn URL |
| `instagram` | string | 1000 | Instagram URL |
| `portfolio` | string | 1000 | Portfolio / GitHub |
| `tags` | string[] | 100 each | Role tags, max 3 |
| `email` | string | 255 | Used as primary lookup key |
| `phone` | string | 255 | Optional |
| `avatar` | string | 1000 | Cloudinary URL or SVG path |

> **Note:** `name`/`full_name` and `role`/`profession` are redundant pairs — both are written on insert/update for backward compatibility.

### 5.2 Collection: `meetups`

| Attribute | Type | Notes |
|---|---|---|
| `title` | string (256) | **Required** |
| `description` | string (4096) | |
| `date` | string (128) | Human-readable, e.g. `"Sunday, June 29th 2026"` |
| `time` | string (128) | e.g. `"9:00 AM – 11:00 AM (IST)"` |
| `venue` | string (256) | |
| `banner_url` | string (1024) | |
| `capacity` | integer | Default: 60 |
| `is_active` | boolean | Default: true |
| `Price` / `price` | integer | **Capitalized** `Price` in DB; default: 422 (INR). Code normalizes on read. |

> ⚠️ **Gotcha:** The price field is stored as `Price` (capital P) in Appwrite but accepted as `price` in the API model. `doc_to_meetup()` handles both via `data.get('Price', data.get('price', 422))`.

### 5.3 Collection: `reservations`

| Attribute | Type | Notes |
|---|---|---|
| `meetup_id` | string (256) | **Required** |
| `user_email` | string (256) | **Required**; used to prevent duplicate registrations |
| `user_name` | string (256) | |
| `quantity` | integer | Number of seats; default: 1 |
| `ticket_id` | string (64) | **Status is encoded here** (see §6) |
| `answers` | string (4096) | JSON-stringified form answers |
| `checked_in` | boolean | Set by ticket scanner |

### 5.4 Collection: `messages`

| Attribute | Type | Notes |
|---|---|---|
| `sender_id` | string (255) | **Required** |
| `receiver_id` | string (255) | **Required** |
| `content` | string (10000) | **Required** |
| `timestamp` | datetime | **Required**; ISO 8601 UTC |

> Schema for `messages` was created manually by running `test_appwrite.py` once. It is NOT created by `seed_meetups.py`.

---

## 6. Ticket ID / Reservation Status Design

> **Important design decision:** There is no dedicated `status` column in the reservations collection. **Status is inferred from the `ticket_id` field value.**

| `ticket_id` value | Derived `status` | Meaning |
|---|---|---|
| `"PENDING"` | `pending_payment` | User registered, awaiting admin to confirm payment |
| `"REJECTED"` | `rejected` | Admin rejected the reservation |
| `"PRNT-EBC-XXXXXX"` | `confirmed` | Approved; this IS the actual ticket ID |

This means:
- **Filtering approved members** (e.g. for the member directory): query reservations and keep only those where `ticket_id` is not `PENDING` and not `REJECTED`.
- **Admin approval** calls `PUT /api/reservations/{id}/approve` → generates `PRNT-EBC-{6 chars}` and writes it as `ticket_id`.
- **Admin rejection** calls `PUT /api/reservations/{id}/reject` → sets `ticket_id = "REJECTED"`.

---

## 7. API Endpoint Reference

All endpoints are prefixed with `/api`. CORS is open to all origins.

### Health
| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Health check; returns `{"status": "ok", "service": "EBC Community API — Perenti"}` |

### Auth
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/auth/login` | Lookup by email in profiles; returns a **mock JWT** (not cryptographically signed) |

> ⚠️ **Security note:** Auth is cosmetic only. The mock token `"mock-jwt-token-for-testing"` is returned for *any* found email with no password validation. This is a known limitation.

### Members
| Method | Path | Query Params | Description |
|---|---|---|---|
| `GET` | `/api/members` | — | Returns only members with an **approved** reservation (ticket not PENDING/REJECTED) |
| `GET` | `/api/members/me` | `?email=` | Fetch own profile by email |
| `GET` | `/api/members/{member_id}` | — | Fetch profile by Appwrite document `$id` |
| `POST` | `/api/members` | — | Create a new member profile |
| `PUT` | `/api/members/{email}` | — | Update profile fields by email |
| `POST` | `/api/members/{member_id}/avatar` | — | Upload image → Cloudinary → update `avatar` field |

### Meetups
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/meetups` | List all meetups |
| `GET` | `/api/meetups/{meetup_id}` | Get single meetup with `registered_count` and `remaining` computed live |
| `POST` | `/api/meetups` | Create a new meetup |
| `PUT` | `/api/meetups/{meetup_id}` | Update meetup details |

### Reservations
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/reservations` | Register for a meetup; checks capacity & duplicate prevention |
| `GET` | `/api/reservations/{meetup_id}` | List confirmed reservations for a meetup |
| `GET` | `/api/reservations/pending` | Admin: list all pending/rejected reservations |
| `GET` | `/api/users/{email}/reservations` | Get all reservations for a user (with embedded meetup data) |
| `PUT` | `/api/reservations/{reservation_id}/status` | Set `checked_in` boolean (scanner use) OR approve/reject |
| `PUT` | `/api/reservations/{reservation_id}/approve` | Admin: approve a pending reservation → generate ticket + send email |
| `PUT` | `/api/reservations/{reservation_id}/reject` | Admin: reject a pending reservation |

> ⚠️ **Duplicate route:** `PUT /api/reservations/{reservation_id}/status` is defined **twice** in `main.py` (lines 644 and 783). FastAPI will use the **last registered** one (line 783), which handles the approve/reject logic. The first definition (line 644) handles `checked_in` toggling and is effectively **shadowed/dead code**.

### Tickets
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/tickets/scan` | QR scan: check-in or check-out a ticket; returns reservation + meetup info |

### Chat
| Method | Path | Query Params | Description |
|---|---|---|---|
| `GET` | `/api/chat/messages` | `?user1=&user2=` | Get all messages between two users (two queries merged + sorted) |
| `POST` | `/api/chat/send` | — | Send a message between two members |

---

## 8. Key Helper Functions in `main.py`

| Function | Purpose |
|---|---|
| `as_dict(obj)` | Normalizes an Appwrite Document (object or dict) to a plain Python dict |
| `get_docs(response)` | Safely extracts the `documents` list from an Appwrite list response |
| `doc_to_member(doc)` | Converts a raw Appwrite document to the standardized member dict shape |
| `doc_to_meetup(doc)` | Converts a raw Appwrite document to the standardized meetup dict shape |
| `doc_to_reservation(doc)` | Converts a raw Appwrite document to reservation dict; **derives status from ticket_id** |
| `optimize_cloudinary_url(url, width)` | Injects Cloudinary URL transformation (`w_N,h_N,c_fill,q_auto,f_auto,r_max`) for circular avatars |
| `send_ticket_email(...)` | Sends HTML email with QR code; falls back gracefully if SMTP not configured |

---

## 9. Data Flow: Member Approval Pipeline

```
User fills Google Form
        │
        ▼
upload_data.py (one-time)
  reads CSV → creates profile docs in Appwrite 'profiles' collection
        │
        ▼
User visits frontend → registers for a meetup
  POST /api/reservations
  { status: "pending_payment" }  →  ticket_id saved as "PENDING"
        │
        ▼
Admin visits admin panel
  GET /api/reservations/pending  →  lists all PENDING reservations
        │
        ├──[Approve]──▶  PUT /api/reservations/{id}/approve
        │                  ticket_id = "PRNT-EBC-XXXXXX"
        │                  email sent to user
        │
        └──[Reject]───▶  PUT /api/reservations/{id}/reject
                           ticket_id = "REJECTED"
        │
        ▼
GET /api/members  →  only shows profiles whose email
                      has an approved (non-PENDING, non-REJECTED) reservation
```

---

## 10. Data Flow: Avatar Upload

```
Frontend picks image file
        │
        ▼
POST /api/members/{member_id}/avatar  (multipart/form-data)
        │
        ▼
Cloudinary upload
  folder: "ebc_avatars"
  public_id: "member_{member_id}"
  transformation: 400×400 face-crop + auto quality/format
        │
        ▼
Update Appwrite document
  { "data": { "avatar": "<cloudinary_secure_url>" } }
        │
        ▼
All subsequent GET /api/members calls run URL through
  optimize_cloudinary_url() → injects w_200,h_200,c_fill,q_auto,f_auto,r_max
```

---

## 11. Pagination Pattern

Appwrite imposes a **max 100 documents per query**. Any endpoint that may return >100 docs uses a cursor-based loop:

```python
queries = [Query.limit(100)]
while True:
    response = databases.list_documents(database_id, COLLECTION, queries)
    docs = get_docs(response)
    if not docs:
        break
    # process docs...
    if len(docs) < 100:
        break
    queries = [Query.limit(100), Query.cursorAfter(docs[-1]['$id'])]
```

This pattern is used in: `GET /api/members`, `GET /api/reservations/pending`.

---

## 12. Admin Emails (Hardcoded)

```python
ADMIN_EMAILS = [
    'admin@perenti.com', 'sreemadhav@gmail.com',
    'madhav@ebc.com', 'shiva24.santosh@gmail.com'
]
```

> ⚠️ These are **defined but not enforced** by any route guard. Admin endpoints (`/approve`, `/reject`, `/pending`) are currently **unauthenticated** — anyone with the URL can call them. This is a known gap.

---

## 13. Deployment (Render)

The service is deployed on **Render** as a Python web service.

- **Config file:** `render.yaml`
- **Build command:** `pip install -r requirements.txt`
- **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Python version:** 3.12.0 (pinned via `PYTHON_VERSION` env var)
- **All secrets** are set as Render environment variables (marked `sync: false` to prevent accidental exposure in `render.yaml`)

### Running Locally

```bash
# 1. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create .env with all required variables (see §4)
cp .env.example .env  # or create manually

# 4. Start the dev server
uvicorn main:app --reload --port 8000

# 5. API docs available at:
#    http://localhost:8000/docs   (Swagger UI)
#    http://localhost:8000/redoc  (ReDoc)
```

---

## 14. One-Time Setup Scripts

These scripts are run **once** during initial project setup or database provisioning. They are **not part of the app runtime**.

| Script | When to Run | What It Does |
|---|---|---|
| `seed_meetups.py` | First deployment / new Appwrite project | Creates `meetups` and `reservations` collections with all attributes; seeds "EBC 28th Meetup" document |
| `upload_data.py` | After `seed_meetups.py`; whenever new CSV data arrives | Reads the Google Form CSV, maps columns to profile fields, inserts into Appwrite `profiles` collection |
| `test_appwrite.py` | Once, if `messages` collection exists but has no attributes | Manually creates the 4 required string/datetime attributes on the `messages` collection |
| `schema_fetch.py` | Debug/discovery | Prints the schema of a given Appwrite collection to stdout |

```bash
# Example: re-seed after schema changes
python seed_meetups.py

# Example: import new batch of form responses
python upload_data.py
```

---

## 15. Testing

Tests use **pytest** with **FastAPI's `TestClient`** (requests to in-process ASGI app — no network needed, but Appwrite credentials must be valid).

```bash
# Run all tests
pytest test_api.py -v

# Run a specific class
pytest test_api.py::TestReservations -v
```

### Test Coverage

| Test Class | What It Covers |
|---|---|
| `TestHealth` | `GET /` returns 200 with status "ok" |
| `TestMembers` | Members list returns list; members have required fields |
| `TestMeetups` | List meetups; get by ID with capacity fields; create meetup; 404 on bad ID |
| `TestReservations` | Empty list for new meetup; create reservation; list includes new; capacity enforcement; count accuracy |
| `TestEdgeCases` | Invalid meetup ID; CORS headers; empty email rejection |

> **Note:** Tests create real data in Appwrite (test meetups with `is_active=False`). There is no teardown — test records accumulate in the database.

---

## 16. Known Issues & Gotchas

| # | Issue | Location | Impact |
|---|---|---|---|
| 1 | **Duplicate route** `PUT /api/reservations/{id}/status` | `main.py` L644 & L783 | L644 (checked_in toggle) is dead code; FastAPI silently uses L783 |
| 2 | **Mock auth** — no real JWT, no password check | `main.py` L114–141 | Any email found in DB logs in successfully; token is a static string |
| 3 | **Admin endpoints are unauthenticated** | `/approve`, `/reject`, `/pending` | Anyone with the URL can approve/reject reservations |
| 4 | **CORS fully open** (`allow_origins=["*"]`) | `main.py` L23–29 | Fine for dev; should be locked down to the frontend domain in production |
| 5 | **`Price` vs `price` inconsistency** | Meetups collection | Appwrite stores `Price` (capital P); code handles both but mutations must map carefully |
| 6 | **Test data not cleaned up** | `test_api.py` | Test meetups persist in Appwrite DB after test runs |
| 7 | **No rate limiting** | All endpoints | Reservation endpoint can be spammed |
| 8 | **`messages` collection not created by seed script** | `test_appwrite.py` | Must be run separately; chat will 500 if collection doesn't exist |

---

## 17. Ticket Format

Confirmed tickets use the format:

```
PRNT-EBC-XXXXXX
```

Where `XXXXXX` is 6 random uppercase alphanumeric characters (A-Z, 0-9).

The QR code URL is: `https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={ticket_id}`

The scanner endpoint `POST /api/tickets/scan` looks up the reservation by `ticket_id` and toggles check-in state.

---

## 18. Naming Conventions

| Concept | Internal name | Notes |
|---|---|---|
| Community / Brand | **Perenti** | Displayed in email, health endpoint, ticket branding |
| Backend repo | **ebc-app-backend** | "EBC" = Ekthaa Business Community (legacy name) |
| Ticket prefix | **PRNT-EBC** | "Perenti" + legacy EBC |
| Admin area | `ADMIN_EMAILS` list | No separate admin role in DB |

---

## 19. Points of Contact / Ownership

- **sreemadhav@gmail.com** — Core contributor (in admin list)
- **shiva24.santosh@gmail.com** — Core contributor (in admin list)

---

## 20. Quick Reference Cheat Sheet

```bash
# Start locally
uvicorn main:app --reload --port 8000

# Run tests
pytest test_api.py -v

# Seed DB (first time)
python seed_meetups.py

# Upload member data from CSV
python upload_data.py

# Create messages collection attributes (first time)
python test_appwrite.py

# Health check
curl http://localhost:8000/

# Get all meetups
curl http://localhost:8000/api/meetups

# Get members (approved only)
curl http://localhost:8000/api/members

# Register for a meetup
curl -X POST http://localhost:8000/api/reservations \
  -H "Content-Type: application/json" \
  -d '{"meetup_id":"<id>","user_email":"test@test.com","user_name":"Test","quantity":1,"answers":"{}"}'

# Admin: list pending reservations
curl http://localhost:8000/api/reservations/pending

# Admin: approve a reservation
curl -X PUT http://localhost:8000/api/reservations/<res_id>/approve
```
