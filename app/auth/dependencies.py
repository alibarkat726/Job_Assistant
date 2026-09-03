from typing import Type, TypeVar, Callable
import uuid
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.db.session import get_db
from app.shared.db.repository import BaseTenantRepository, Base
from app.shared.security.jwt import decode_access_token
from app.shared.middleware.error_handler import AuthenticationError
from app.users.models import User
from app.users.repository import UserRepository
from app.auth.services import AuthService

security_scheme = HTTPBearer()
ModelT = TypeVar("ModelT", bound=Base)
RepoT = TypeVar("RepoT", bound=BaseTenantRepository)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate JWT access token from Bearer header."""
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise AuthenticationError("Invalid or expired access token.")

    try:
        user_id = uuid.UUID(payload["sub"])
    except ValueError:
        raise AuthenticationError("Invalid user ID in token claim.")

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise AuthenticationError("User associated with token not found.")

    if user.is_locked():
        raise AuthenticationError("Account is locked.")

    return user


async def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    """Dependency injection for AuthService."""
    user_repo = UserRepository(db)
    return AuthService(user_repo)


def get_tenant_repo(repo_cls: Type[RepoT]) -> Callable[..., RepoT]:
    """
    Factory dependency for injecting tenant-scoped repository instances into endpoints.
    Ensures every tenant endpoint automatically gets a repository bound to the authenticated user!
    """

    async def _dependency(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> RepoT:
        return repo_cls(db=db, tenant_id=current_user.id)

    return _dependency
