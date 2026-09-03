from fastapi import APIRouter, Depends, Request, status
from app.shared.middleware.rate_limiter import limiter
from app.users.schemas import UserResponse
from app.users.models import User
from app.auth.schemas import (
    UserRegister,
    UserLogin,
    TokenResponse,
    RefreshTokenRequest,
    VerifyEmailRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
    MessageResponse,
)
from app.auth.services import AuthService
from app.auth.dependencies import get_auth_service, get_current_user

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request,
    dto: UserRegister,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Register a new user account."""
    user_response, _ = await auth_service.register(dto)
    return user_response


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    dto: UserLogin,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Authenticate user credentials and return JWT token pair."""
    return await auth_service.login(dto)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh_tokens(
    request: Request,
    dto: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Rotate refresh token and issue a new access token."""
    return await auth_service.refresh_tokens(dto.refresh_token)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    dto: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Revoke user refresh token."""
    await auth_service.logout(dto.refresh_token)
    return MessageResponse(message="Successfully logged out.")


@router.post("/verify-email", response_model=UserResponse)
async def verify_email(
    dto: VerifyEmailRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Verify email address with token."""
    return await auth_service.verify_email(dto.token)


@router.post("/request-password-reset", response_model=MessageResponse)
@limiter.limit("3/minute")
async def request_password_reset(
    request: Request,
    dto: PasswordResetRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Request a password reset link email."""
    await auth_service.request_password_reset(dto.email)
    return MessageResponse(
        message="If an account with that email exists, a password reset link has been sent."
    )


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    dto: PasswordResetConfirm,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Confirm password reset using token."""
    await auth_service.reset_password(dto)
    return MessageResponse(message="Password reset successful. Please log in with your new password.")


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
):
    """Fetch profile of currently authenticated user."""
    return UserResponse.model_validate(current_user)
