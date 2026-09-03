from datetime import datetime, timedelta, timezone
import logging
from typing import Dict, Tuple
from app.config.settings import settings
from app.shared.security.hashing import hash_password, verify_password
from app.shared.security.jwt import (
    create_access_token,
    generate_opaque_token,
    hash_opaque_token,
)
from app.shared.middleware.error_handler import (
    AppException,
    AuthenticationError,
    AccountLockedError,
)
from app.users.models import User, RefreshToken
from app.users.repository import UserRepository
from app.users.schemas import UserResponse
from app.auth.schemas import (
    UserRegister,
    UserLogin,
    TokenResponse,
    PasswordResetConfirm,
)

logger = logging.getLogger(__name__)


class AuthService:
    """Service layer encapsulating authentication, session management, and password security."""

    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    async def register(self, dto: UserRegister) -> Tuple[UserResponse, str]:
        """Register a new user, issue email verification token, and stub verification email."""
        existing_user = await self.user_repo.get_by_email(dto.email)
        if existing_user:
            raise AppException(
                message="User with this email already exists.",
                code="USER_ALREADY_EXISTS",
                status_code=409,
            )

        hashed_pw = hash_password(dto.password)
        raw_verification_token = generate_opaque_token()
        token_hash = hash_opaque_token(raw_verification_token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

        user = User(
            email=dto.email.lower().strip(),
            hashed_password=hashed_pw,
            is_verified=False,
            verification_token_hash=token_hash,
            verification_token_expires_at=expires_at,
        )
        created_user = await self.user_repo.create(user)

        # Stub email dispatch
        logger.info(
            f"[EMAIL STUB] Verification email sent to {user.email}. Verification Token: {raw_verification_token}"
        )

        return UserResponse.model_validate(created_user), raw_verification_token

    async def login(self, dto: UserLogin) -> TokenResponse:
        """Authenticate user credentials, handle account lockout, and issue access/refresh token pair."""
        user = await self.user_repo.get_by_email(dto.email)
        if not user:
            # Constant-time dummy verify to prevent timing attack enumeration
            verify_password("dummy_password", "$argon2id$v=19$m=65536,t=3,p=4$dummy$dummy")
            raise AuthenticationError("Invalid email or password.")

        if user.is_locked():
            raise AccountLockedError(
                f"Account locked due to consecutive failed attempts. Try again after {user.locked_until}."
            )

        if not verify_password(dto.password, user.hashed_password):
            # Increment failed attempts
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
                user.locked_until = datetime.now(timezone.utc) + timedelta(
                    minutes=settings.ACCOUNT_LOCKOUT_MINUTES
                )
                logger.warning(f"Account for user {user.id} locked due to failed login attempts.")
            await self.user_repo.update(user)
            raise AuthenticationError("Invalid email or password.")

        # Reset failed login attempts on successful authentication
        if user.failed_login_attempts > 0 or user.locked_until is not None:
            user.failed_login_attempts = 0
            user.locked_until = None
            await self.user_repo.update(user)

        return await self._create_tokens_for_user(user)

    async def refresh_tokens(self, raw_refresh_token: str) -> TokenResponse:
        """Verify refresh token, perform rotation (revoke old, issue new pair), and return tokens."""
        token_hash = hash_opaque_token(raw_refresh_token)
        rt_record = await self.user_repo.get_refresh_token_by_hash(token_hash)

        if not rt_record or not rt_record.is_active:
            raise AuthenticationError("Invalid, expired, or revoked refresh token.")

        # Revoke the used refresh token (Rotation!)
        await self.user_repo.revoke_refresh_token(token_hash)

        # Get user
        user = await self.user_repo.get_by_id(rt_record.user_id)
        if not user or user.is_locked():
            raise AuthenticationError("User account is inactive or locked.")

        # Issue new token pair
        return await self._create_tokens_for_user(user)

    async def logout(self, raw_refresh_token: str) -> None:
        """Revoke user's refresh token on logout."""
        token_hash = hash_opaque_token(raw_refresh_token)
        await self.user_repo.revoke_refresh_token(token_hash)

    async def verify_email(self, raw_token: str) -> UserResponse:
        """Verify user's email with provided token."""
        token_hash = hash_opaque_token(raw_token)
        user = await self.user_repo.get_by_verification_token_hash(token_hash)

        if not user or not user.verification_token_expires_at:
            raise AppException("Invalid or expired email verification token.", code="INVALID_TOKEN", status_code=400)

        if datetime.now(timezone.utc) > user.verification_token_expires_at:
            raise AppException("Verification token has expired.", code="TOKEN_EXPIRED", status_code=400)

        user.is_verified = True
        user.verification_token_hash = None
        user.verification_token_expires_at = None
        updated_user = await self.user_repo.update(user)
        return UserResponse.model_validate(updated_user)

    async def request_password_reset(self, email: str) -> None:
        """Generate password reset token and stub reset email (enumeration-safe)."""
        user = await self.user_repo.get_by_email(email)
        if user:
            raw_reset_token = generate_opaque_token()
            token_hash = hash_opaque_token(raw_reset_token)
            expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

            user.password_reset_token_hash = token_hash
            user.password_reset_token_expires_at = expires_at
            await self.user_repo.update(user)

            logger.info(
                f"[EMAIL STUB] Password reset link sent to {user.email}. Reset Token: {raw_reset_token}"
            )

    async def reset_password(self, dto: PasswordResetConfirm) -> None:
        """Reset password using valid reset token and revoke existing sessions."""
        token_hash = hash_opaque_token(dto.token)
        user = await self.user_repo.get_by_password_reset_token_hash(token_hash)

        if not user or not user.password_reset_token_expires_at:
            raise AppException("Invalid or expired password reset token.", code="INVALID_TOKEN", status_code=400)

        if datetime.now(timezone.utc) > user.password_reset_token_expires_at:
            raise AppException("Password reset token has expired.", code="TOKEN_EXPIRED", status_code=400)

        # Update password and clear reset fields
        user.hashed_password = hash_password(dto.new_password)
        user.password_reset_token_hash = None
        user.password_reset_token_expires_at = None
        user.failed_login_attempts = 0
        user.locked_until = None
        await self.user_repo.update(user)

        # Revoke all existing refresh tokens for security
        await self.user_repo.revoke_all_user_refresh_tokens(user.id)

    async def _create_tokens_for_user(self, user: User) -> TokenResponse:
        """Internal helper to issue signed JWT access token and save hashed refresh token."""
        access_token = create_access_token(subject=str(user.id))

        raw_refresh_token = generate_opaque_token()
        refresh_token_hash = hash_opaque_token(raw_refresh_token)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        rt_entity = RefreshToken(
            user_id=user.id,
            token_hash=refresh_token_hash,
            expires_at=expires_at,
        )
        await self.user_repo.save_refresh_token(rt_entity)

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
