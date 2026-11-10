# FairNest Setup Guide (Docker & Local)

This guide covers setting up and running the complete **FairNest** stack (MongoDB replica set `rs0`, FastAPI backend, 30-second lifecycle worker, and React frontend) using either **Docker Compose** or a **Local (Native)** environment.

---

## Domain & Default Demo Accounts

FairNest is configured for the institutional domain **`iitbhilai.demo`** (`ALLOWED_EMAIL_DOMAINS=iitbhilai.demo`):

| Account / Script | Default Email | Password | Notes |
|---|---|---|---|
| **Super Admin** (`scripts/create_super_admin.py`) | `admin@iitbhilai.demo` | Entered interactively (≥ 12 chars) | Full system access (`SUPER_ADMIN`) |
| **Demo Students** (`scripts/load_demo_data.py`) | `student1@iitbhilai.demo` … `student300@iitbhilai.demo` | `demo_password_123` | 300 active students across 4 hostels (`BH1`, `BH2`, `GH1`, `GH2`) |

> When `ALLOWED_EMAIL_DOMAINS` is non-empty (such as `iitbhilai.demo`), CSV student imports and role grants reject emails outside that domain.

---

## Step 1: Create `.env` at the Repository Root

Copy the template file from the repository root (`FairNest/`):

```bash
cp .env.example .env
```

Review [`.env.example`](.env.example) and set values for your chosen setup:

| Variable | Docker Compose Value | Local (Atlas / Native) Value | Purpose |
|---|---|---|---|
| `MONGO_URI` | `mongodb://mongo:27017/?replicaSet=rs0` | Atlas: `mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/?appName=Cluster0`<br>Local `mongod`: `mongodb://localhost:27017/?replicaSet=rs0` | Replica-set URI required for multi-document ACID transactions. |
| `MONGO_DB` | `hostel_allotment` | `hostel_allotment` | Target MongoDB database name. |
| `JWT_SECRET` | Change to a random 32+ char string | Change to a random 32+ char string | HS256 JWT signing secret. |
| `BOOTSTRAP_SUPER_ADMIN_EMAIL` | `admin@iitbhilai.demo` | `admin@iitbhilai.demo` | Default Super Admin account email. |
| `ALLOWED_EMAIL_DOMAINS` | `iitbhilai.demo` | `iitbhilai.demo` | Allowed institutional email domain(s), comma-separated. |
| `CORS_ORIGINS` | `http://localhost:5173` | `http://localhost:5173` | Allowed frontend origin(s). |

> **Important:** Place `.env` at the **repository root** (`FairNest/.env`). The backend config ([`backend/app/core/config.py`](backend/app/core/config.py)) automatically resolves the root `.env` even when running scripts or servers from inside `backend/`.

---

## Option A: Docker Compose Setup (Recommended)

### Prerequisites
- Docker Engine & Docker Compose v2 (`docker compose version`)
- Ports `5173`, `8000`, and `27017` free on your machine

### 1. Build & Start All Services
From the repository root (`FairNest/`):

```bash
docker compose up --build -d
# or using Makefile:
make up
```

This starts 4 containers:
- `mongo` (`mongo:7` configured with `--replSet rs0` and automatic `rs.initiate()`)
- `backend` (FastAPI API on port `8000`)
- `worker` (30-second hold-expiry, window-scheduler, and invariant-check worker)
- `frontend` (React production build served by Nginx on port `5173`, proxying `/api/*` → `backend:8000`)

Wait until the containers are healthy (`docker compose ps`).

### 2. Bootstrap Super Admin & Load Demo Data
```bash
docker compose exec backend python scripts/create_super_admin.py
docker compose exec backend python scripts/load_demo_data.py
# or run both at once:
make seed
```

### 3. Access the Application
- **Web UI:** <http://localhost:5173>
- **API Readiness Probe:** <http://localhost:8000/api/v1/health/ready>
- **API Swagger Docs:** <http://localhost:8000/api/docs>

### 4. Useful Docker Commands
```bash
# Follow API & Worker logs
docker compose logs -f backend worker

# Stop containers (keep MongoDB data volume)
docker compose down

# Stop containers and wipe MongoDB data volume
docker compose down -v
```

---

## Option B: Local (Native) Setup Without Docker

### Prerequisites
- **Python 3.11+** with `venv` (`python3-venv`)
- **Node.js 18+** & `npm`
- **MongoDB Replica Set (`rs0`)** — either MongoDB Atlas or a local `mongod` instance (standalone non-replica-set `mongod` will fail on transactions)

### 1. Set Up MongoDB (`rs0`)

Choose **one** of the following:

#### 1A. MongoDB Atlas (Cloud)
1. Create a free M0 cluster in MongoDB Atlas (Atlas clusters run as a 3-node replica set out of the box).
2. Under **Database Access**, create a database user with read/write access on `hostel_allotment` (or Atlas admin).
3. Under **Network Access**, allow your current public IP (or `0.0.0.0/0` for development).
4. Put your `mongodb+srv://...` connection string in root `.env` as `MONGO_URI`.

#### 1B. Local `mongod` Replica Set (`rs0`)
Start `mongod` with `--replSet rs0` (in a dedicated terminal or background service):

```bash
mkdir -p ~/mongo-fairnest-data
mongod --replSet rs0 --dbpath ~/mongo-fairnest-data --port 27017 --bind_ip 127.0.0.1
```

In another terminal, initialize the single-node replica set once:

```bash
mongosh --port 27017 --eval 'rs.initiate({_id: "rs0", members: [{_id: 0, host: "localhost:27017"}]})'
```

Set `MONGO_URI=mongodb://localhost:27017/?replicaSet=rs0` in root `.env`.

### 2. Set Up the Backend Virtual Environment
Use a local virtual environment inside `backend/venv` (avoids system PEP 668 restrictions):

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Bootstrap Super Admin & Load Demo Data
With `(venv)` active inside `FairNest/backend`:

```bash
python3 scripts/create_super_admin.py
python3 scripts/load_demo_data.py
```

- `create_super_admin.py` prompts for a password (minimum 12 characters) and creates `admin@iitbhilai.demo` (`SUPER_ADMIN`), plus all indexes and schema validators.
- `load_demo_data.py` seeds 4 hostels (`BH1`, `BH2`, `GH1`, `GH2`), 5 floors per hostel, ~100 beds, and 300 active demo students (`student1@iitbhilai.demo` … `student300@iitbhilai.demo`, password `demo_password_123`).

### 4. Start API, Worker, and Frontend (3 Separate Terminals)

**Terminal 1 — FastAPI Backend (`http://localhost:8000`):**
```bash
cd FairNest/backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — Background Lifecycle Worker:**
```bash
cd FairNest/backend
source venv/bin/activate
python -m app.worker
```

**Terminal 3 — Vite Frontend Dev Server (`http://localhost:5173`):**
```bash
cd FairNest/frontend
npm install
npm run dev
```

*(Vite automatically proxies `/api/*` requests to `http://localhost:8000` via [`frontend/vite.config.js`](frontend/vite.config.js).)*

---

## First Login & Quick Smoke Walkthrough

1. Open **<http://localhost:5173>** and sign in as Super Admin:
   - **Email:** `admin@iitbhilai.demo`
   - **Password:** the password you entered in `create_super_admin.py`
2. Open **Rooms** in the left sidebar (`/warden/rooms`) to verify all 4 hostels (`BH1`, `BH2`, `GH1`, `GH2`), floors, and rooms are visible.
3. Open **Roles & Access** (`/superadmin/roles`) if you want to assign `WARDEN`, `ADMIN`, or `AUDITOR` roles to `@iitbhilai.demo` emails.
4. Open **Cycles** (`/admin/cycles`) → **+ New Cycle** → pick a hostel, create a cycle, and click **Open Now**.
   - *(Note: Students see "No active cycle" on their dashboard until at least one cycle is created and opened for their hostel.)*
5. Sign in as a demo student (`student1@iitbhilai.demo` or roll `20240001`, password `demo_password_123`) to form groups, rank preferences, and test allocation.

---

## Running Tests & Verification Scripts

```bash
# Backend unit tests (no DB required)
cd backend && source venv/bin/activate && pytest tests/unit -v

# Full backend test suite (unit + integration + concurrency + security; requires MongoDB rs0)
cd backend && source venv/bin/activate && pytest -v

# Containerized CI test run (isolated test MongoDB rs0)
make test

# Simulator unit & determinism tests (no DB required)
cd simulator && PYTHONPATH=../backend:. pytest -v

# Operational DB & cryptographic checks (from backend/ with venv active)
python3 scripts/check_invariants.py
python3 scripts/verify_allocation.py --cycle <CYCLE_ID>
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `[Errno 98] Address already in use` on port `8000` | Another `uvicorn`, background server, or `root`-owned Docker container holds port `8000`. | Inspect with `sudo lsof -i :8000` and `sudo docker ps --filter "publish=8000"`. Stop container with `sudo docker compose down` / `sudo docker stop <id>`, or kill process with `sudo fuser -k 8000/tcp`. |
| `source .venv/bin/activate: no such file` or `PEP 668 externally-managed-environment` | Virtual environment folder is `venv` (not `.venv`), or pip ran outside the venv. | Inside `backend/`: run `python3 -m venv venv && source venv/bin/activate`. |
| `ServerSelectionTimeoutError` connecting to `localhost:27017` or Atlas | Local `mongod` isn't running with `rs0`, or Atlas Network Access blocks your IP. | Check `MONGO_URI` in root `.env`, ensure your IP is whitelisted in Atlas Network Access, or start local `mongod --replSet rs0` and run `rs.initiate(...)`. |
| `Hostels` tab shows empty after seeding | Logged in as scoped `WARDEN`/`ADMIN` with empty `managed_hostel_ids`, or running outdated backend code. | Sign in as `SUPER_ADMIN` (`admin@iitbhilai.demo`), or assign `managed_hostel_ids` under **Roles & Access**. |
