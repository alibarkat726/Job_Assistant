from fastapi import FastAPI
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

app = FastAPI(
    title=settings.APP_NAME,
    description="Job-Finder AI Agent Platform - Auth & Multi-Tenant Foundation",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
)

# Attach Slowapi Limiter state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 1. Security Headers Middleware
app.add_middleware(SecurityHeadersMiddleware)

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


@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "environment": settings.ENVIRONMENT}
