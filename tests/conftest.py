import asyncio
from typing import AsyncGenerator
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from sqlalchemy import text
from app.config.settings import settings
settings.ENVIRONMENT = "testing"
from app.shared.middleware.rate_limiter import limiter
limiter.enabled = False

from app.shared.db.session import get_db
from app.users.repository import UserRepository
from app.auth.schemas import UserRegister
from app.auth.services import AuthService
from app.main import app

test_engine = create_async_engine(
    settings.TEST_DATABASE_URL,
    poolclass=NullPool,
    echo=False,
)

TestAsyncSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provides a fresh, isolated database session for each test."""
    async with test_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE users, refresh_tokens, cvs, skills, projects, project_skills, learning_entries, learning_proposals, proposed_skill_items, job_applications, jd_requirements, application_skill_matches, tailored_cvs, interview_prep_sets, interview_questions, cover_letters, document_chunks, chat_sessions, chat_messages CASCADE;"
            )
        )

    async with TestAsyncSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE users, refresh_tokens, cvs, skills, projects, project_skills, learning_entries, learning_proposals, proposed_skill_items, job_applications, jd_requirements, application_skill_matches, tailored_cvs, interview_prep_sets, interview_questions, cover_letters, document_chunks, chat_sessions, chat_messages CASCADE;"
            )
        )


@pytest.fixture(scope="function")
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provides an AsyncClient for testing FastAPI endpoints with overridden db dependency."""

    async def _override_get_db():
        # Match production: each request gets a separate session and immutable
        # tenant binding, including when a test exercises two different users.
        async with TestAsyncSessionLocal() as request_session:
            try:
                yield request_session
                await request_session.commit()
            except Exception:
                await request_session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
async def test_user_a(db_session: AsyncSession):
    """Creates Test User A."""
    repo = UserRepository(db_session)
    service = AuthService(repo)
    user_resp, _ = await service.register(
        UserRegister(email="user_a@example.com", password="Password123!")
    )
    tokens = await service.login(
        UserRegister(email="user_a@example.com", password="Password123!")
    )
    await db_session.commit()
    return {"user": user_resp, "tokens": tokens}


@pytest.fixture(scope="function")
async def test_user_b(db_session: AsyncSession):
    """Creates Test User B."""
    repo = UserRepository(db_session)
    service = AuthService(repo)
    user_resp, _ = await service.register(
        UserRegister(email="user_b@example.com", password="Password123!")
    )
    tokens = await service.login(
        UserRegister(email="user_b@example.com", password="Password123!")
    )
    await db_session.commit()
    return {"user": user_resp, "tokens": tokens}
