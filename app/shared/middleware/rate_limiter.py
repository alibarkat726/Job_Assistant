from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.config.settings import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
    enabled=settings.ENVIRONMENT != "testing",
    storage_uri=settings.RATE_LIMIT_STORAGE_URI,
)


def authenticated_rate_key(request: Request) -> str:
    return "user:" + getattr(request.state, "user_id", get_remote_address(request))


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": f"Rate limit exceeded: {exc.detail}",
                "details": None,
            }
        },
    )
