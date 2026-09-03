from datetime import datetime, timezone
from typing import Optional
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.db.repository import BaseRepository
from app.users.models import User, RefreshToken


class UserRepository(BaseRepository[User]):
    def __init__(self, db: AsyncSession):
        super().__init__(User, db)

    async def get_by_email(self, email: str) -> Optional[User]:
        """Fetch user by email (case-insensitive search)."""
        stmt = select(User).filter(User.email == email.lower().strip())
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_verification_token_hash(self, token_hash: str) -> Optional[User]:
        """Fetch user by verification token hash."""
        stmt = select(User).filter(User.verification_token_hash == token_hash)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_password_reset_token_hash(self, token_hash: str) -> Optional[User]:
        """Fetch user by password reset token hash."""
        stmt = select(User).filter(User.password_reset_token_hash == token_hash)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def save_refresh_token(self, refresh_token: RefreshToken) -> RefreshToken:
        """Store a new refresh token entity."""
        self.db.add(refresh_token)
        await self.db.flush()
        return refresh_token

    async def get_refresh_token_by_hash(self, token_hash: str) -> Optional[RefreshToken]:
        """Fetch refresh token record by token hash."""
        stmt = select(RefreshToken).filter(RefreshToken.token_hash == token_hash)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke_refresh_token(self, token_hash: str) -> None:
        """Revoke a refresh token by setting revoked_at timestamp."""
        now = datetime.now(timezone.utc)
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .values(revoked_at=now)
        )
        await self.db.execute(stmt)
        await self.db.flush()

    async def revoke_all_user_refresh_tokens(self, user_id: uuid.UUID) -> None:
        """Revoke all active refresh tokens for a given user."""
        now = datetime.now(timezone.utc)
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await self.db.execute(stmt)
        await self.db.flush()
