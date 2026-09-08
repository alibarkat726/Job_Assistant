# Job-Finder AI Agent Platform - Module 1 (Auth & Multi-Tenant) & Module 2 (CV Intake)

This repository provides **Module 1 (Auth + Multi-Tenant Foundation)** and **Module 2 (CV Intake & Structured Storage)** for the Job-Finder AI Agent Platform. Built with **Python, FastAPI, PostgreSQL, SQLAlchemy 2.0 (Async), Alembic**, and **uv**.

---

## 🏛️ Architecture & Folder Structure

The project follows a clean layered architecture designed to allow engineers to drop in new domain modules by following established patterns.

```
job_assitant/
├── app/
│   ├── main.py                     # FastAPI application entry point & middleware wiring
│   ├── config/
│   │   └── settings.py             # Single source of truth config (pydantic-settings)
│   ├── shared/
│   │   ├── db/
│   │   │   ├── base.py             # SQLAlchemy DeclarativeBase & TimestampMixin
│   │   │   ├── session.py          # Async Engine & Session maker
│   │   │   └── repository.py       # BaseRepository & BaseTenantRepository (Systemic isolation)
│   │   ├── middleware/
│   │   │   ├── error_handler.py    # Centralized exception handling & error payload shaping
│   │   │   ├── security_headers.py # Standard security headers middleware (CSP, HSTS, X-Frame-Options)
│   │   │   └── rate_limiter.py     # Slowapi rate limiter
│   │   └── security/
│   │       ├── hashing.py          # Argon2id password hashing helpers
│   │       └── jwt.py              # Signed JWT access token & opaque refresh token hashing
│   ├── users/
│   │   ├── models.py               # User & RefreshToken SQLAlchemy models
│   │   ├── schemas.py              # Pydantic response models
│   │   └── repository.py           # UserRepository
│   ├── auth/
│   │   ├── schemas.py              # Auth input/output validation schemas
│   │   ├── services.py             # AuthService (Registration, Login, Lockout, Token Rotation)
│   │   ├── dependencies.py         # get_current_user & get_tenant_repo dependency factory
│   │   └── routes.py               # Auth HTTP API endpoints (/register, /login, /refresh, /logout, etc.)
│   ├── cv/                         # Module 2: CV Intake & Structured Storage
│   │   ├── storage.py              # FileStorageService abstract interface & LocalStorageService
│   │   ├── security.py             # Magic bytes MIME sniffer, size validator, bleach HTML sanitizer
│   │   ├── extractor.py            # Text extraction for PDF (pypdf), DOCX (python-docx), and TXT
│   │   ├── schemas.py              # Pydantic structured CV, draft edit, and upload models
│   │   ├── parser.py               # Intake Agent (ICVParser, HeuristicCVParser, LLMCVParser)
│   │   ├── repository.py           # Tenant-scoped CVRepository & child table operations
│   │   ├── services.py             # CVIntakeService (upload, parse, edit draft, finalize, download, delete)
│   │   └── routes.py               # CV HTTP endpoints (/upload, /me, /draft, /finalize, /raw)
│   ├── skills/                     # Module 3: Profile Skills CRUD
│   │   ├── schemas.py
│   │   ├── repository.py
│   │   ├── services.py
│   │   └── routes.py
│   ├── projects/                   # Module 3: Portfolio Projects CRUD
│   │   ├── schemas.py
│   │   ├── repository.py
│   │   ├── services.py
│   │   └── routes.py
│   ├── learning/                   # Module 4: Daily Learning Log & Triage Agent
│   │   ├── schemas.py
│   │   ├── repository.py
│   │   ├── triage_agent.py         # ITriageAgent interface & heuristic classifier
│   │   ├── services.py             # Orchestrates Agent and Human-in-the-Loop approvals
│   │   └── routes.py
│   ├── tailoring/                  # Module 5: Job Applications & CV Tailoring
│   │   ├── schemas.py
│   │   ├── repository.py
│   │   ├── jd_parser.py            # IJDParser interface & HeuristicJDParser
│   │   ├── matching.py             # Pure slug-overlap scoring engine (no LLM)
│   │   ├── tailoring_agent.py      # ITailoringAgent interface & HeuristicTailoringAgent
│   │   ├── services.py             # Orchestrates JD parse → match → tailor → finalize
│   │   └── routes.py
│   └── core_schema/
│       └── models.py               # Domain models (CV, Skill, Project, LearningEntry, JobApplication, etc.)
├── alembic/                        # Versioned DB migrations with Postgres RLS FORCE policies
│   ├── env.py
│   └── versions/
│       ├── 001_initial_multitenant_schema.py
│       └── 002_cv_intake_schema.py
├── storage/                        # Local file storage (outside web root)
│   └── cvs/                        # <user_uuid>/<file_uuid>
├── tests/
│   ├── conftest.py                 # Pytest async fixtures
│   ├── unit/
│   │   ├── test_auth_service.py    # Auth service unit tests
│   │   ├── test_security.py        # Security unit tests
│   │   ├── test_cv_security.py     # File sniffing, size limit & HTML sanitization tests
│   │   ├── test_cv_storage.py      # Storage service & path traversal tests
│   │   └── test_cv_parser.py       # Intake Agent & heuristic parser tests
│   └── integration/
│       ├── test_tenant_isolation.py # Tenant isolation integration tests (App layer & Postgres RLS)
│       └── test_cv_intake.py       # Full CV intake workflow & tenant isolation integration tests
├── .env.example
├── pyproject.toml
└── README.md
```

---

## 📄 Module 2: CV Intake & Parsing Workflow

Module 2 provides end-to-end CV upload, raw file storage, automated parsing into structured domain data, user review/edit capabilities, and canonical profile finalization.

### 1. Upload & File Security Pipeline
- **Endpoint**: `POST /api/v1/cvs/upload`
- **File Validation**: Server-side file size enforcement (max 10MB) and content sniffing (inspects magic bytes for PDF `%PDF-`, DOCX `PK\x03\x04`, and UTF-8 plain text). Rejects spoofed extensions.
- **Secure File Storage**: Files are saved in `./storage/cvs/<user_uuid>/<file_uuid>` outside any static file server root via `LocalStorageService` (implementing `FileStorageService`).
- **Text Extraction**: Uses `pypdf` for PDFs, `python-docx` for DOCX, and UTF-8 decoder for TXT files.

### 2. Intake Agent & Fallback Parsing Chain
- **Decoupled Architecture**: `IntakeAgentService` orchestrates parsing behind an `ICVParser` interface.
- **Parsing Chain**:
  1. Executes `LLMCVParser` (if `LLM_API_KEY` is configured) and validates response against `StructuredCVSchema`.
  2. On error or schema validation failure: automatically logs a warning and executes `HeuristicCVParser` fallback.
  3. Returns `parse_confidence` metadata (`high`, `medium`, `low`) and `parsing_notes` to guide user review.
- **Sanitization**: All extracted strings are sanitized with `bleach.clean` to prevent HTML/XSS injection when rendered later.

### 3. Review / Edit & Finalization Workflow
Parsing CVs is failure-prone. First-pass extractions are saved as unfinalized drafts (`is_canonical=False`):
1. **Upload**: Returns parsed draft data for review.
2. **Review/Edit**: User can update parsed contact info, work history, education, or skills via `PUT /api/v1/cvs/draft`.
3. **Finalize**: User calls `POST /api/v1/cvs/finalize` to commit the draft into their canonical active CV (`is_canonical=True`).
4. **Fetch**: `GET /api/v1/cvs/me` returns the user's active canonical profile or draft.
5. **Download Raw**: `GET /api/v1/cvs/raw` streams the original uploaded file (with tenant ownership check).
6. **Delete**: `DELETE /api/v1/cvs/me` deletes the active CV, child records, and raw storage file (`204 No Content`).

---

## 🛠️ Module 3: Skills & Projects (Profile Management)

Module 3 builds the canonical user profile foundation required for future Matching and Tailoring modules. It implements tenant-scoped CRUD operations for skills and portfolio projects, with a strong emphasis on data normalization and tenant isolation.

### 1. Skill Normalization & CV Integration
- **Canonical Skills**: The `skills` table represents the user's authoritative profile skills (used for matching), conceptually separate from `cv_skills` (the raw historical extraction tied to an uploaded CV).
- **Normalization Engine**: All skills are normalized to a `name_slug` (lowercase, stripped, collapsed whitespace). E.g., `"React.js"` → `"react.js"`. 
- **Conflict Prevention**: A unique constraint on `(user_id, name_slug)` prevents duplicate entries across cases or spacing variations. The API returns `409 Conflict` on duplicates.
- **Proficiency**: Tracks user confidence on a `1-5` integer scale (mapped to `0.0-1.0` weights later in Module 6).
- **Promotion Flow**: The service exposes an internal `upsert_skill(source="cv_import")` method, allowing future modules (like Learning Triage) to programmatically promote skills from CV extractions to the canonical profile without HTTP overhead.

### 2. Portfolio Projects & Many-to-Many Associations
- **Projects CRUD**: Full lifecycle management for portfolio projects, capturing title, description, dates, and ongoing status.
- **JSONB URL Storage**: Project URLs (repo, live demo, case study) are stored cleanly in a Postgres `JSONB` column, avoiding unnecessary secondary join tables while maintaining Pydantic schema validation.
- **Tenant-Safe Many-to-Many**: Projects and Skills are linked via the `project_skills` association table.
  - **RLS Forced**: The join table includes `user_id` and enforces strict Row Level Security.
  - **Cross-Tenant Attack Guard**: The API actively validates that both the project and the skill belong to the authenticated user before allowing attachment, preventing ID-guessing enumeration attacks.

---

## 🧠 Module 4: Learning Triage Agent (Daily Learning Log)

Module 4 allows users to log their daily learning activities and utilizes an AI Triage Agent to classify them and propose updates to the canonical skill profile (Module 3). It strictly follows a "Human-in-the-Loop" architecture.

### 1. Human-in-the-Loop Approval Flow
- **Triage Proposals**: The `TriageAgent` evaluates learning entries and generates a `LearningProposal`. Instead of blindly writing to the `skills` table, the agent stages the proposals (with proposed actions `create_new` or `reinforce_existing`).
- **Partial Approvals**: Users review pending proposals via `/api/v1/learning/proposals/pending` and can explicitly approve individual skill proposals while rejecting others within the same entry.
- **Skill Mutation Guard**: The agent *never* mutates the canonical profile directly. Only explicit human approval calls `SkillsService.upsert_skill`.

### 2. Confidence & Decay Semantics (Graph Engine)
To prevent the "stale skills" problem in the Matching Engine, skill proficiency follows these explicit semantics:
- **Agent Confidence vs. Proficiency**: The Triage Agent's confidence (`high`, `medium`, `low`) is decoupled from the user's canonical `proficiency`. Agent confidence represents *certainty in the extraction*, whereas proficiency represents *actual demonstrated ability*.
- **Creation Floor**: Approved new skills (`create_new`) *always* start at a proficiency of `1` (on the 1-5 scale), ignoring agent confidence.
- **Reinforcement Increment**: When an existing skill is reinforced (`reinforce_existing`) via learning, its canonical proficiency is incremented by `+1` (capped at 5) and its `updated_at` (recency) timestamp is refreshed. (Note: These rules generalize across reinforcement sources; if projects eventually reinforce skills, they should share this logic).
- **Lazy Decay (Designed, Not Scheduled)**: To avoid silent cron-job failures, decay is designed to be *lazy computed at read-time* (e.g. `effective_proficiency = stored_proficiency - floor(months_since_update / 6)`). The proficiency cannot decay below a floor of `1`, since past reinforcement implies baseline capability.

---

## 🎯 Module 5: Job Applications & CV Tailoring

Module 5 allows users to paste a job description, receive a structured analysis against their skill graph and portfolio, and generate a tailored CV draft — all without any automated job scraping or third-party submissions.

### 1. JD Intake & Parsing
- **Endpoint**: `POST /api/v1/applications` — user pastes the raw JD text (title, company optional, source URL optional).
- **JD Parser**: Runs `HeuristicJDParser` (same interface-driven pattern as `ICVParser` and `ITriageAgent`) to extract required skills/technologies, seniority level, and key responsibilities.
- **Normalized Child Table**: Extracted requirements are stored as rows in `jd_requirements` (not a JSON blob), consistent with Module 2's pattern. Each row has `skill_name`, `skill_slug` (normalized for matching), `is_required`, and `seniority`.
- **Validation Failure**: On parser error, the application is marked `needs_manual_review` rather than crashing.

### 2. Matching Engine (Slug-Overlap Scoring)
- **Endpoint**: `GET /api/v1/applications/{id}/match`
- **Strategy**: Pure deterministic slug-overlap scoring — no LLM required. Each JD requirement's `skill_slug` is compared against the user's canonical `skills.name_slug` using the same `normalize_skill_name` function from Module 3.
- **Result Tiers**:
  - `matched` — exact slug match found in user's skill graph
  - `partial` — the JD slug contains or is contained by a user skill slug (e.g. user has `node.js`, JD asks for `node`)
  - `missing` — no match found
- **Overall Score**: Based on required skills only (nice-to-have misses do not penalize the score).
- **Project Ranking**: Projects are ranked by how many of their attached skills match the JD's requirements, using the Module 3 `project_skills` many-to-many relationship.
- **Future Upgrade Path**: Semantic/embedding-based matching (e.g. `Backend` matching `FastAPI`) is a documented future upgrade that can be layered without changing this engine's interface.

### 3. Tailoring Agent & Immutable Facts Rule
- **Endpoint**: `POST /api/v1/applications/{id}/tailor`
- **Hard Constraint**: The agent may **only reorder, reweight, or rephrase** existing verified CV data. It must **never invent** experience, skills, metrics, company names, dates, or URLs not already present in the canonical CV.
- **Enforcement**: Underlying facts (company, role, dates, project URLs) are copied verbatim from the canonical CV record. Only the **order** of work history entries changes — entries mentioning matched JD skills are surfaced first.
- **Top Projects**: Up to 3 portfolio projects are selected based on their JD relevance score.

### 4. Draft / Edit / Finalize Flow (mirrors Module 2)
1. **Tailor**: Agent generates a draft linked to the job application.
2. **Review/Edit**: User can update `tailored_content` or `selected_project_ids` via `PUT /api/v1/applications/{id}/tailor`.
3. **Finalize**: `POST /api/v1/applications/{id}/tailor/finalize` — commits the tailored CV version permanently to the application record (providing a history of what was sent for each job).

### 5. Manual "Applied" Status
- The application status flows: `draft` → `tailored` → `applied`.
- The `applied` status is **manually set by the user** via `PUT /api/v1/applications/{id}/status` once they have submitted externally.
- This system **never auto-submits** to third-party job sites.

---

## 🔒 Security Design & Highlights


1. **Password Hashing**: Argon2id via `pwdlib` and `argon2-cffi`. Passwords are never logged or exposed in API response models.
2. **Session Management (JWT + DB Refresh Tokens)**:
   - **Access Token**: Short-lived (15 minutes) signed JWT containing `sub` (User ID), `iat`, `exp`, `jti` (UUID), `type`.
   - **Refresh Token**: High-entropy opaque random string. SHA-256 hash stored in DB with 7-day expiration.
   - **Token Rotation**: Every refresh invalidates/revokes the old refresh token and issues a fresh pair.
   - **Logout**: Revokes the refresh token.
3. **Account Lockout & Brute-Force Protection**:
   - Accounts track consecutive failed login attempts. After 5 failed attempts, the account is locked for 15 minutes (`locked_until`).
4. **Rate Limiting**: Applied to auth endpoints and `/api/v1/cvs/upload` (5/min) via `slowapi`.
5. **Security Headers & CORS**: Explicit CORS origin whitelist, CSP, HSTS, X-Frame-Options (`DENY`), X-Content-Type-Options (`nosniff`), Referrer Policy.

---

## 🛡️ Multi-Tenant Isolation Guarantee (Double-Layer Defense)

Tenant isolation is enforced across two independent layers:

### Layer 1: Application Layer (`BaseTenantRepository`)
Every tenant-owned domain repository extends `BaseTenantRepository[ModelT]`.
- Requires `tenant_id: uuid.UUID` on instantiation.
- Automatically applies `.filter(Model.user_id == self.tenant_id)` to every `SELECT`, `UPDATE`, and `DELETE` query.
- Automatically attaches `user_id = self.tenant_id` on all inserts.

### Layer 2: PostgreSQL Row-Level Security (RLS)
Every tenant table (`cvs`, `work_histories`, `education_entries`, `cv_skills`, `skills`, `projects`, `learning_entries`, `jobs_cache`, `applications`) has Postgres RLS enabled and forced:
```sql
ALTER TABLE <table_name> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <table_name> FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_policy ON <table_name>
FOR ALL USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);
```

---

## 🚀 How to Setup and Run

### 1. Prerequisites
- Python >= 3.12
- [`uv`](https://github.com/astral-sh/uv)
- PostgreSQL database running locally or in Docker

### 2. Environment Setup
```bash
cp .env.example .env
# Edit .env with your PostgreSQL credentials and JWT secret key
```

### 3. Install Dependencies
```bash
uv sync
```

### 4. Run Database Migrations
```bash
# Run migrations on dev database
uv run alembic upgrade head

# Run migrations on test database
DATABASE_URL=postgresql+asyncpg://postgres@localhost:5432/job_assistant_test_db uv run alembic upgrade head
```

### 5. Start Application Server
```bash
uv run uvicorn app.main:app --reload --port 8000
```
- API Documentation: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/health`

---

## 🧪 Running Tests

Execute the full suite of unit and integration tests:
```bash
uv run pytest
```

Tests include:
- Auth & security unit tests (Argon2id, JWT, token rotation, account lockout)
- CV Intake unit tests (file size validation, magic byte sniffing, HTML sanitization, local file storage path traversal protection, Intake Agent heuristic parsing)
- Skills/Projects unit tests (normalization, deduplication, project-skill many-to-many, cross-tenant guard)
- Learning Triage unit tests (heuristic classification, approval mutations, partial approval, reinforcement increment)
- JD Parser unit tests (skill extraction, seniority detection, required vs nice-to-have)
- Matching Engine unit tests (matched/partial/missing scoring, project ranking, overall score calculation)
- Tailoring Agent unit tests (verbatim facts invariant, reordering, top-3 project selection)
- Multi-Tenant Integration tests (User A vs User B tenant isolation at both application repository and PostgreSQL RLS layers)
- Full workflow integration: upload → edit → finalize → download → delete (CV), create → learn → propose → approve → canonical skill update (Learning), submit JD → parse → match → tailor → finalize (Tailoring)
