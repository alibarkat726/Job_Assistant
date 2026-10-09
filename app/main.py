from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from sqlalchemy import text
from app.shared.db.session import engine
from app.shared.middleware.request_id import RequestIDMiddleware
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from app.config.settings import settings
from app.shared.middleware.error_handler import register_exception_handlers
from app.shared.middleware.security_headers import SecurityHeadersMiddleware
from app.shared.middleware.rate_limiter import limiter, _rate_limit_exceeded_handler
from app.auth.routes import router as auth_router
from app.cv.routes import router as cv_router
from app.skills.routes import router as skills_router
from app.projects.routes import router as projects_router
from app.learning.routes import router as learning_router
from app.tailoring.routes import router as tailoring_router
from app.interview_prep.routes import router as interview_prep_router
from app.dashboard.routes import router as dashboard_router
from app.cover_letters.routes import router as cover_letter_router
from app.rag.routes import router as rag_router


@asynccontextmanager
async def lifespan(application):
    if settings.ENVIRONMENT == "production":
        # Refuse to serve with a bypass role or incomplete rollout, even if the
        # deployment forgot to configure readiness routing.
        await readiness_check()
    try:
        yield
    finally:
        from app.rag.embedding import embedding_service
        from app.rag.quota import quota_client
        if "client" in embedding_service.__dict__:
            await embedding_service.client.close()
        if quota_client.cache_info().currsize:
            await quota_client().aclose()
        await engine.dispose()

app = FastAPI(
    lifespan=lifespan,
    title=settings.APP_NAME,
    description="Job-Finder AI Agent Platform - Auth & Multi-Tenant Foundation",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT in ("development", "testing") else None,
    redoc_url="/redoc" if settings.ENVIRONMENT in ("development", "testing") else None,
)

# Attach Slowapi Limiter state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 1. Security Headers Middleware
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)

# 2. CORS Middleware (Explicit origins configuration)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)

# 3. Register Centralized Exception Handlers
register_exception_handlers(app)

# 4. Include Routers
app.include_router(auth_router)
app.include_router(cv_router)
app.include_router(skills_router)
app.include_router(projects_router)
app.include_router(learning_router)
app.include_router(tailoring_router)
app.include_router(interview_prep_router)
app.include_router(dashboard_router)
app.include_router(cover_letter_router)
app.include_router(rag_router)


@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "environment": settings.ENVIRONMENT}


@app.get("/ready", tags=["System"])
async def readiness_check():
    try:
        async with engine.connect() as conn:
            role = (await conn.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"))).one()
            if settings.ENVIRONMENT == "production" and any(role):
                raise RuntimeError("Unsafe database role")
            if settings.ENVIRONMENT == "production" and await conn.scalar(text("""
                SELECT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relrowsecurity AND has_table_privilege(c.oid, 'TRUNCATE'))
            """)):
                raise RuntimeError("Runtime role has tenant-table TRUNCATE privileges")
            version = await conn.scalar(text("SELECT version_num FROM alembic_version"))
            if version != "010_rag_production":
                raise RuntimeError("Migration required")
            if not await conn.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")):
                raise RuntimeError("Vector extension required")
            if settings.ENVIRONMENT == "production":
                from app.rag.quota import quota_client
                await quota_client().ping()
        return {"status": "ready"}
    except Exception:
        raise HTTPException(503, "Service dependencies are not ready.") from None
