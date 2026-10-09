"""Run with python -m app.rag.worker using DATABASE_URL for the rag_worker role."""
import argparse
import asyncio
import logging
import time

from sqlalchemy import text
from app.shared.db.session import AsyncSessionLocal, engine
from app.shared.db.tenant import bind_tenant
from app.rag.ingestion import RAGIngestionService, IndexChanged
from app.rag.repository import RAGRepository
from app.rag.embedding import embedding_service
from app.config.settings import settings

logger = logging.getLogger(__name__)


async def run_once(batch_size=25):
    # Discovery is allowed only to the dedicated worker role by a narrow queue policy.
    async with AsyncSessionLocal() as db:
        result = await db.execute(text('''
            SELECT user_id FROM rag_index_jobs WHERE next_attempt_at <= now()
            ORDER BY next_attempt_at, user_id LIMIT :limit
        '''), {'limit': batch_size})
        user_ids = list(result.scalars())
    completed = 0
    for user_id in user_ids:
        started = time.monotonic()
        async with AsyncSessionLocal() as db:
            await bind_tenant(db, user_id)
            acquired = await db.scalar(text('SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))'),
                                       {'key': f'rag:{user_id}'})
            if not acquired:
                continue
            repo = RAGRepository(db)
            revision = await repo.get_index_revision(user_id)
            if revision is None:
                continue
            try:
                count = await RAGIngestionService(db).sync_all_user_data(user_id)
                await db.execute(text('DELETE FROM rag_index_jobs WHERE user_id = :uid AND revision = :revision'),
                                 {'uid': user_id, 'revision': revision})
                await db.commit()
                completed += 1
                logger.info('rag_index_completed chunks=%d duration_ms=%d', count, int((time.monotonic() - started) * 1000))
            except Exception as exc:
                await db.rollback()  # Previous chunks survive failed replacement.
                if isinstance(exc, IndexChanged):
                    logger.info('rag_index_changed retry_pending=true')
                    continue
                # Do not persist exception messages, documents, or provider request data.
                await db.execute(text('''
                    UPDATE rag_index_jobs SET attempts = attempts + 1, last_error = :error,
                    next_attempt_at = now() + make_interval(secs => LEAST(3600, 30 * power(2, LEAST(attempts, 7)))::int)
                    WHERE user_id = :uid AND revision = :revision
                '''), {'uid': user_id, 'revision': revision, 'error': type(exc).__name__[:100]})
                await db.commit()
                logger.warning('rag_index_failed error_type=%s', type(exc).__name__)
    return completed


async def main(once=False):
    try:
        async with engine.connect() as conn:
            role = (await conn.execute(text('SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user'))).one()
            if role[0] != 'rag_worker' or role[1] or role[2]:
                raise RuntimeError('Worker requires the rag_worker role without SUPERUSER or BYPASSRLS.')
        while True:
            await run_once()
            if once:
                break
            await asyncio.sleep(5)
    finally:
        from app.rag.quota import quota_client
        if quota_client.cache_info().currsize:
            await quota_client().aclose()
        if 'client' in embedding_service.__dict__:
            await embedding_service.client.close()
        await engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    logging.basicConfig(level=settings.LOG_LEVEL)
    asyncio.run(main(parser.parse_args().once))
