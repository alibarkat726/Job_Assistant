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
│   └── core_schema/
│       └── models.py               # Domain models (CV, WorkHistory, EducationEntry, Skill, Project, etc.)
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
- Multi-Tenant Integration tests (User A vs User B tenant isolation at both application repository and PostgreSQL RLS layers, full upload → edit → finalize → download → delete workflow)
