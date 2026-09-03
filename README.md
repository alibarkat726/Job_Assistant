# Job-Finder AI Agent Platform - Module 1: Auth & Multi-Tenant Foundation

This repository provides **Module 1 (Auth + Multi-Tenant Foundation)** for the Job-Finder AI Agent Platform. Built with **Python, FastAPI, PostgreSQL, SQLAlchemy 2.0 (Async), Alembic**, and **uv**.

---

## 🏛️ Architecture & Folder Structure

The project follows a clean layered architecture designed to allow second engineers to drop in new domain modules (e.g., `skills/`, `projects/`, `jobs/`) by following established patterns.

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
│   │   │   └── rate_limiter.py     # Slowapi rate limiter for auth endpoints
│   │   └── security/
│   │       ├── hashing.py          # Argon2id password hashing helpers
│   │       └── jwt.py              # Signed JWT access token & opaque refresh token hashing
│   ├── users/
│   │   ├── models.py               # User & RefreshToken SQLAlchemy models
│   │   ├── schemas.py              # Pydantic response models (passwords never exposed)
│   │   └── repository.py           # UserRepository
│   ├── auth/
│   │   ├── schemas.py              # Register, Login, Refresh, Password Reset input validation schemas
│   │   ├── services.py             # AuthService (Registration, Login, Lockout, Token Rotation)
│   │   ├── dependencies.py         # get_current_user & get_tenant_repo dependency factory
│   │   └── routes.py               # Auth HTTP API endpoints (/register, /login, /refresh, /logout, etc.)
│   └── core_schema/
│       └── models.py               # Empty/minimal multi-tenant domain models (cvs, skills, projects, etc.)
├── alembic/                        # Versioned DB migrations with Postgres RLS policies
│   ├── env.py
│   └── versions/
│       └── 001_initial_multitenant_schema.py
├── tests/
│   ├── conftest.py                 # Pytest async fixtures
│   ├── unit/
│   │   ├── test_auth_service.py    # Auth service unit tests
│   │   └── test_security.py      # Security unit tests
│   └── integration/
│       └── test_tenant_isolation.py # Tenant isolation integration tests (App layer & Postgres RLS)
├── .env.example
├── pyproject.toml
└── README.md
```

---

## 🔒 Security Design & Highlights

1. **Password Hashing**: Argon2id via `pwdlib` and `argon2-cffi`. Passwords are never logged or exposed in API response models.
2. **Session Management (JWT + DB Refresh Tokens)**:
   - **Access Token**: Short-lived (15 minutes) signed JWT containing `sub` (User ID), `iat`, `exp`, `jti` (UUID), `type`.
   - **Refresh Token**: High-entropy opaque random string. SHA-256 hash stored in DB with 7-day expiration.
   - **Token Rotation**: Every refresh invalidates/revokes the old refresh token and issues a fresh pair.
   - **Logout**: Revokes the refresh token.
3. **Account Lockout & Brute-Force Protection**:
   - Accounts track consecutive failed login attempts. After 5 failed attempts, the account is locked for 15 minutes (`locked_until`). Resets automatically on successful authentication.
4. **Rate Limiting**: Applied to `/auth/register` (5/min), `/auth/login` (5/min), `/auth/request-password-reset` (3/min), `/auth/reset-password` (5/min) via `slowapi`.
5. **Security Headers & CORS**: Explicit CORS origin whitelist, CSP, HSTS, X-Frame-Options (`DENY`), X-Content-Type-Options (`nosniff`), Referrer Policy.

---

## 🛡️ Multi-Tenant Isolation Guarantee (Double-Layer Defense)

Tenant isolation is implemented as a **systemic guarantee** across two independent layers so developers cannot accidentally leak data across tenants:

### Layer 1: Application Layer (`BaseTenantRepository`)
Every tenant-owned domain repository extends `BaseTenantRepository[ModelT]`.
- Requires `tenant_id: uuid.UUID` on instantiation.
- Automatically applies `.filter(Model.user_id == self.tenant_id)` to every `SELECT`, `UPDATE`, and `DELETE` query.
- Automatically attaches `user_id = self.tenant_id` on all inserts.

```python
# Extending BaseTenantRepository for a new module (e.g., Projects)
class ProjectRepository(BaseTenantRepository[Project]):
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        super().__init__(Project, db, tenant_id)
```

In route handlers, inject tenant repositories using `get_tenant_repo`:
```python
@router.get("/projects", response_model=List[ProjectResponse])
async def list_projects(
    repo: ProjectRepository = Depends(get_tenant_repo(ProjectRepository))
):
    return await repo.find_all()
```

### Layer 2: PostgreSQL Row-Level Security (RLS)
Every tenant table (`cvs`, `skills`, `projects`, `learning_entries`, `jobs_cache`, `applications`) has Postgres RLS enabled (`ENABLE ROW LEVEL SECURITY; FORCE ROW LEVEL SECURITY;`).

Policy definition in Alembic migration:
```sql
CREATE POLICY tenant_isolation_policy ON <table_name>
FOR ALL
USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);
```
`BaseTenantRepository` sets `SET LOCAL app.current_user_id = '<user_id>'` inside the session transaction. Even raw SQL queries executed by non-superusers cannot read or modify rows belonging to another `user_id`.

---

## 🚀 How to Setup and Run

### 1. Prerequisite
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

# (Optional) Run migrations on test database
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
- Security unit tests (password hashing, JWT creation/decoding, opaque token hashing)
- Auth service unit tests (registration, login, failed attempt account lockout, refresh token rotation, logout, email verification)
- Integration tests proving multi-tenant isolation at both `BaseTenantRepository` level and PostgreSQL RLS policy level.
