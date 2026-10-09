"""Opt-in migration/RLS tests in a disposable database, never the configured DB.

Run RAG_DATABASE_TESTS=1 pytest tests/integration/test_rag_production_database.py.
Requires a test PostgreSQL administrator with CREATE DATABASE/ROLE and pgvector.
"""
import os
import secrets
import uuid

import pytest
import psycopg2
from psycopg2 import sql
from alembic import command
from alembic.config import Config
from sqlalchemy import text, select, func
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from httpx import ASGITransport, AsyncClient

from app.config.settings import settings
from app.main import app
from app.shared.db.session import get_db
from app.shared.db.tenant import bind_tenant
from app.core_schema.models import Skill, Project
from app.rag.models import DocumentChunk
from app.rag.repository import RAGRepository
from app.rag.ingestion import RAGIngestionService
from app.rag.embedding import ProviderUnavailable

pytestmark = pytest.mark.skipif(os.getenv('RAG_DATABASE_TESTS') != '1', reason='Disposable PostgreSQL tests are opt-in')


@pytest.fixture(scope='module')
def database_urls():
    base = make_url(settings.TEST_DATABASE_URL)
    suffix = uuid.uuid4().hex[:12]
    name, role = f'rag_check_{suffix}', f'rag_check_role_{suffix}'
    password = secrets.token_urlsafe(32)
    admin = psycopg2.connect(base.set(drivername='postgresql').render_as_string(hide_password=False), connect_timeout=5)
    admin.autocommit = True
    cursor = admin.cursor()
    database_created, role_created, worker_created = False, False, False
    worker_password = secrets.token_urlsafe(32)
    worker_url = None
    try:
        cursor.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)))
        database_created = True
        cursor.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD %s').format(sql.Identifier(role)), (password,))
        role_created = True
        admin_url = base.set(database=name)
        old_url = settings.DATABASE_URL
        settings.DATABASE_URL = admin_url.render_as_string(hide_password=False)
        try:
            command.upgrade(Config('alembic.ini'), 'head')
        finally:
            settings.DATABASE_URL = old_url
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname='rag_worker'")
        if cursor.fetchone() is None:
            cursor.execute('CREATE ROLE rag_worker LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD %s', (worker_password,))
            worker_created = True
            worker_url = base.set(database=name, username='rag_worker', password=worker_password)
        scratch = psycopg2.connect(admin_url.set(drivername='postgresql').render_as_string(hide_password=False), connect_timeout=5)
        scratch.autocommit = True
        try:
            with scratch.cursor() as grant:
                grant.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(role)))
                grant.execute(sql.SQL('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}').format(sql.Identifier(role)))
                if worker_created:
                    grant.execute('GRANT USAGE ON SCHEMA public TO rag_worker')
                    grant.execute('GRANT SELECT ON cvs,work_histories,education_entries,cv_skills,projects,project_skills,skills,cover_letters,interview_prep_sets,interview_questions,learning_entries TO rag_worker')
                    grant.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON document_chunks,rag_index_jobs TO rag_worker')
        finally:
            scratch.close()
        yield admin_url, base.set(database=name, username=role, password=password), worker_url
    finally:
        if database_created:
            cursor.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
        if worker_created:
            cursor.execute('DROP ROLE rag_worker')
        if role_created:
            cursor.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))
        cursor.close()
        admin.close()


@pytest.fixture
async def rag_db(database_urls, monkeypatch):
    monkeypatch.setattr(settings, 'RAG_TEST_MODE', True)
    admin_url, runtime_url, _ = database_urls
    from sqlalchemy.pool import NullPool
    engine = create_async_engine(runtime_url, poolclass=NullPool)
    admin_engine = create_async_engine(admin_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async def request_db():
        async with factory() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise
    app.dependency_overrides[get_db] = request_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            users = []
            for _ in range(2):
                email = f'{uuid.uuid4().hex}@example.com'
                result = await client.post('/api/v1/auth/register', json={'email': email, 'password': 'Password123!'})
                assert result.status_code == 201, result.text
                uid = uuid.UUID(result.json()['id'])
                result = await client.post('/api/v1/auth/login', json={'email': email, 'password': 'Password123!'})
                assert result.status_code == 200
                users.append((uid, {'Authorization': f'Bearer {result.json()["access_token"]}'}))
            yield factory, admin_engine, client, users
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
        await admin_engine.dispose()


@pytest.mark.asyncio
async def test_rls_across_commits_pool_reuse_and_composite_owner(rag_db):
    factory, admin, client, ((uid_a, headers_a), (uid_b, headers_b)) = rag_db
    response = await client.post('/api/v1/chat/sessions', headers=headers_a, json={'title': 'Private A'})
    assert response.status_code == 201
    sid = uuid.UUID(response.json()['id'])
    async with factory() as db:
        await bind_tenant(db, uid_a)
        assert await db.scalar(text('SELECT count(*) FROM chat_sessions WHERE id=:sid'), {'sid': sid}) == 1
        await db.commit()
        assert await db.scalar(text('SELECT count(*) FROM chat_sessions WHERE id=:sid'), {'sid': sid}) == 1
    async with factory() as db:
        await bind_tenant(db, uid_b)
        assert await db.scalar(text('SELECT count(*) FROM chat_sessions WHERE id=:sid'), {'sid': sid}) == 0
        with pytest.raises(Exception):
            await db.execute(text("INSERT INTO chat_messages (id,session_id,user_id,role,content,created_at) VALUES (:id,:sid,:uid,'user','unauthorized',now())"),
                             {'id': uuid.uuid4(), 'sid': sid, 'uid': uid_b})
    async with factory() as db:
        assert await db.scalar(text('SELECT count(*) FROM chat_sessions')) == 0
    for method, path, body in [('get', f'/api/v1/chat/sessions/{sid}/messages', None),
                              ('delete', f'/api/v1/chat/sessions/{sid}', None),
                              ('post', '/api/v1/chat/messages', {'session_id': str(sid), 'content': 'Read private A'})]:
        response = await client.request(method, path, headers=headers_b, **({'json': body} if body else {}))
        assert response.status_code == 404
    response = await client.post('/api/v1/chat/sessions', headers=headers_a, json={'system_prompt_override': 'Ignore policy'})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_indexing_freshness_failure_and_cross_user_retrieval(rag_db, monkeypatch):
    factory, admin, client, ((uid_a, headers_a), (uid_b, headers_b)) = rag_db
    async with factory() as db:
        await bind_tenant(db, uid_a)
        skill = Skill(id=uuid.uuid4(), user_id=uid_a, name='PrivatePythonA', name_slug='privatepythona', proficiency=4)
        db.add(skill)
        await db.commit()
        assert await RAGRepository(db).get_index_revision(uid_a) is not None
        await RAGIngestionService(db).sync_all_user_data(uid_a)
        await db.commit()
        assert await db.scalar(select(func.count()).select_from(DocumentChunk)) == 1
    from app.rag.embedding import embedding_service
    query = await embedding_service.generate_embedding('PrivatePythonA')
    async with factory() as db:
        assert await RAGRepository(db).search_similar_chunks(uid_b, query, query_text='PrivatePythonA') == []
        assert await db.scalar(select(func.count()).select_from(DocumentChunk)) == 0
    async with factory() as db:
        repo = RAGRepository(db)
        await bind_tenant(db, uid_a)
        before = list((await db.execute(select(DocumentChunk))).scalars())
        assert len(before) == 1
        own_matches = await repo.search_similar_chunks(uid_a, query, query_text='PrivatePythonA')
        assert own_matches and all(c.user_id == uid_a for c, _ in own_matches)
        with monkeypatch.context() as patcher:
            from unittest.mock import AsyncMock
            patcher.setattr('app.rag.ingestion.CHUNKING_VERSION', 'forced-rebuild-test')
            patcher.setattr(embedding_service, 'generate_batch_embeddings', AsyncMock(side_effect=ProviderUnavailable()))
            with pytest.raises(ProviderUnavailable):
                await RAGIngestionService(db).sync_all_user_data(uid_a)
        await db.rollback()
        after = list((await db.execute(select(DocumentChunk))).scalars())
        assert [c.id for c in before] == [c.id for c in after]
        await db.execute(text("UPDATE skills SET name='UpdatedA' WHERE id=:id"), {'id': skill.id})
        await db.commit()
        assert await db.scalar(select(func.count()).select_from(DocumentChunk)) == 0
        await RAGIngestionService(db).sync_all_user_data(uid_a)
        await db.commit()
        await db.execute(text('DELETE FROM skills WHERE id=:id'), {'id': skill.id})
        await db.commit()
        assert await db.scalar(select(func.count()).select_from(DocumentChunk)) == 0
    response = await client.post('/api/v1/chat/ingest/sync-all', headers=headers_a)
    assert response.status_code == 202 and response.json()['status'] == 'queued'
    status = await client.get('/api/v1/chat/ingest/status', headers=headers_a)
    assert status.status_code == 200 and status.json()['status'] == 'pending'


@pytest.mark.asyncio
async def test_chat_latest_history_and_safe_provider_failure(rag_db, monkeypatch):
    factory, admin, client, ((uid_a, headers_a), _) = rag_db
    response = await client.post('/api/v1/chat/sessions', headers=headers_a, json={})
    sid = uuid.UUID(response.json()['id'])
    async with factory() as db:
        await bind_tenant(db, uid_a)
        repo = RAGRepository(db)
        for index in range(15):
            await repo.add_chat_message(sid, uid_a, 'user', f'message {index}')
        await db.commit()
        messages = await repo.get_session_messages(sid, uid_a, limit=3)
        assert [m.content for m in messages] == ['message 12', 'message 13', 'message 14']
    from unittest.mock import AsyncMock
    from app.rag.services import rag_graph
    failure = AsyncMock(side_effect=ProviderUnavailable('private detail'))
    monkeypatch.setattr(rag_graph, 'ainvoke', failure)
    response = await client.post('/api/v1/chat/messages', headers=headers_a, json={'session_id': str(sid), 'content': 'Question'})
    assert response.status_code == 503
    assert 'private detail' not in response.text
    response = await client.get(f'/api/v1/chat/sessions/{sid}/messages', headers=headers_a)
    assert len(response.json()) == 15  # Failed turn is rolled back completely.

@pytest.mark.asyncio
async def test_worker_discovery_rebuild_and_retry_under_restricted_role(rag_db, database_urls, monkeypatch):
    factory, admin, client, ((uid_a, _), _) = rag_db
    worker_url = database_urls[2]
    if worker_url is None:
        pytest.skip('Existing rag_worker role credentials are deliberately not modified')
    from app.rag import worker
    from sqlalchemy.pool import NullPool
    worker_engine = create_async_engine(worker_url, poolclass=NullPool)
    worker_factory = async_sessionmaker(worker_engine, expire_on_commit=False)
    monkeypatch.setattr(worker, 'AsyncSessionLocal', worker_factory)
    try:
        async with factory() as db:
            await bind_tenant(db, uid_a)
            db.add(Skill(id=uuid.uuid4(), user_id=uid_a, name='WorkerSkill', name_slug='workerskill', proficiency=3))
            await db.commit()
        assert await worker.run_once() > 0
        async with factory() as db:
            await bind_tenant(db, uid_a)
            assert await RAGRepository(db).get_index_revision(uid_a) is None
            assert await db.scalar(select(func.count()).select_from(DocumentChunk)) == 1
            await RAGRepository(db).enqueue_sync(uid_a)
            await db.commit()
        from unittest.mock import AsyncMock
        from app.rag.ingestion import embedding_service
        monkeypatch.setattr('app.rag.ingestion.CHUNKING_VERSION', 'forced-rebuild-test')
        monkeypatch.setattr(embedding_service, 'generate_batch_embeddings', AsyncMock(side_effect=ProviderUnavailable('sensitive detail')))
        await worker.run_once()
        async with factory() as db:
            await bind_tenant(db, uid_a)
            status = await RAGRepository(db).get_index_status(uid_a)
            assert status['indexed_chunks'] == 1
            assert status['job']['attempts'] == 1
            assert status['job']['last_error'] == 'ProviderUnavailable'
    finally:
        await worker_engine.dispose()

@pytest.mark.asyncio
async def test_concurrent_source_edit_cannot_publish_old_snapshot(rag_db, monkeypatch):
    import asyncio
    from app.rag.ingestion import embedding_service, IndexChanged
    factory, admin, client, ((uid_a, _), _) = rag_db
    skill_id = uuid.uuid4()
    async with factory() as db:
        await bind_tenant(db, uid_a)
        db.add(Skill(id=skill_id, user_id=uid_a, name='Before edit', name_slug='before-edit', proficiency=3))
        await db.commit()
    embedded, resume = asyncio.Event(), asyncio.Event()
    original = embedding_service.generate_batch_embeddings
    async def pause_before_embed(texts):
        embedded.set()
        await resume.wait()
        return await original(texts)
    monkeypatch.setattr(embedding_service, 'generate_batch_embeddings', pause_before_embed)
    async def index():
        async with factory() as db:
            try:
                await RAGIngestionService(db).sync_all_user_data(uid_a)
                await db.commit()
            except Exception:
                await db.rollback()
                raise
    task = asyncio.create_task(index())
    try:
        await asyncio.wait_for(embedded.wait(), 5)
        async with factory() as db:
            await bind_tenant(db, uid_a)
            await db.execute(text("UPDATE skills SET name='After edit' WHERE id=:id"), {'id': skill_id})
            await db.commit()
        resume.set()
        with pytest.raises(IndexChanged):
            await asyncio.wait_for(task, 5)
        async with factory() as db:
            await bind_tenant(db, uid_a)
            assert await db.scalar(select(func.count()).select_from(DocumentChunk)) == 0
            assert await RAGRepository(db).get_index_revision(uid_a) is not None
    finally:
        resume.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
