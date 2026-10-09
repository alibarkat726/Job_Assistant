import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.shared.db.repository import BaseTenantRepository
from app.core_schema.models import Project, CV, Skill


@pytest.mark.asyncio
async def test_tenant_isolation_at_repository_layer(
    db_session: AsyncSession, test_user_a, test_user_b
):
    """
    Integration Test: BaseTenantRepository Isolation.
    Proves User B CANNOT read, update, or delete User A's data.
    """
    user_a_id = test_user_a["user"].id
    user_b_id = test_user_b["user"].id

    repo_a = BaseTenantRepository(Project, db_session, tenant_id=user_a_id)

    # 1. User A creates a project
    project_a = Project(title="User A's Secret AI Agent Architecture")
    created_a = await repo_a.create(project_a)
    await db_session.commit()

    assert created_a.id is not None
    assert created_a.user_id == user_a_id

    async with AsyncSession(db_session.bind, expire_on_commit=False) as session_b:
        repo_b = BaseTenantRepository(Project, session_b, tenant_id=user_b_id)
        # 2. User B tries to fetch User A's project by ID -> Must return None!
        project_b_view = await repo_b.get_by_id(created_a.id)
        assert project_b_view is None

        # 3. User B tries to list all projects -> Must return 0 items!
        all_b_projects = await repo_b.find_all()
        assert len(all_b_projects) == 0

        # 4. User A lists projects -> Must return 1 item
        all_a_projects = await repo_a.find_all()
        assert len(all_a_projects) == 1
        assert all_a_projects[0].id == created_a.id

        # 5. User B attempts to delete User A's record -> Must raise PermissionError
        with pytest.raises(PermissionError):
            await repo_b.delete(created_a)


@pytest.mark.asyncio
async def test_tenant_isolation_at_postgres_rls_layer(
    test_user_a, test_user_b
):
    """
    Integration Test: PostgreSQL Row-Level Security (RLS) Policy Enforcement.
    Proves that non-superuser database connections strictly enforce Postgres RLS policies,
    preventing User B from reading User A's data even with a raw SQL query.
    """
    user_a_id = test_user_a["user"].id
    user_b_id = test_user_b["user"].id

    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.pool import NullPool

    # Connect as non-superuser 'app_user' to validate RLS policy enforcement
    non_super_url = "postgresql+asyncpg://app_user:app_password@localhost:5432/job_assistant_test_db"
    non_super_engine = create_async_engine(non_super_url, poolclass=NullPool)

    async with AsyncSession(non_super_engine, expire_on_commit=False) as session_a:
        repo_a = BaseTenantRepository(CV, session_a, tenant_id=user_a_id)
        cv_a = CV(title="User A Master Resume")
        created_cv = await repo_a.create(cv_a)
        await session_a.commit()
        cv_id = created_cv.id

    async with AsyncSession(non_super_engine) as session_b:
        # Direct raw query as User B setting app.current_user_id
        await session_b.execute(text("SELECT set_config('app.current_user_id', :uid, false)"), {"uid": str(user_b_id)})
        res_b = await session_b.execute(text("SELECT * FROM cvs WHERE id = :id"), {"id": str(cv_id)})
        b_rows = res_b.fetchall()
        assert len(b_rows) == 0, "Postgres RLS leaked User A's data to User B!"

    async with AsyncSession(non_super_engine) as session_a2:
        # Direct raw query as User A setting app.current_user_id
        await session_a2.execute(text("SELECT set_config('app.current_user_id', :uid, false)"), {"uid": str(user_a_id)})
        res_a = await session_a2.execute(text("SELECT * FROM cvs WHERE id = :id"), {"id": str(cv_id)})
        a_rows = res_a.fetchall()
        assert len(a_rows) == 1, "User A should be able to query their own data via Postgres RLS."

    await non_super_engine.dispose()
