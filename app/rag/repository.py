from sqlalchemy import select, delete, text, and_, exists, func, or_
from app.rag.models import DocumentChunk, ChatSession, ChatMessage
from app.rag.embedding import embedding_service
from app.shared.db.tenant import bind_tenant


class RAGRepository:
    def __init__(self, db):
        self.db = db

    async def replace_source_chunks(self, user_id, source_type, source_id, chunks):
        await bind_tenant(self.db, user_id)
        if any(c.user_id != user_id or c.source_id != source_id or c.source_type != source_type for c in chunks):
            raise PermissionError('Invalid chunk ownership.')
        async with self.db.begin_nested():
            await self.delete_chunks_by_source(user_id, source_type, source_id)
            self.db.add_all(chunks)
            await self.db.flush()

    async def delete_chunks_by_source(self, user_id, source_type, source_id):
        await bind_tenant(self.db, user_id)
        result = await self.db.execute(delete(DocumentChunk).where(
            DocumentChunk.user_id == user_id, DocumentChunk.source_type == source_type,
            DocumentChunk.source_id == source_id))
        return result.rowcount

    async def get_source_chunks(self, user_id, source_type, source_id):
        await bind_tenant(self.db, user_id)
        result = await self.db.execute(select(DocumentChunk).where(
            DocumentChunk.user_id == user_id, DocumentChunk.source_type == source_type,
            DocumentChunk.source_id == source_id).order_by(DocumentChunk.chunk_index))
        return list(result.scalars().all())

    def _live_source_condition(self):
        from app.rag.ingestion import SOURCES
        return or_(*[and_(DocumentChunk.source_type == kind, exists(select(model.id).where(
            model.id == DocumentChunk.source_id, model.user_id == DocumentChunk.user_id)))
            for kind, model in SOURCES.items()])

    async def prune_deleted_sources(self, user_id):
        await bind_tenant(self.db, user_id)
        await self.db.execute(delete(DocumentChunk).where(
            DocumentChunk.user_id == user_id, ~self._live_source_condition()))

    async def search_similar_chunks(self, user_id, query_embedding, source_types=None,
                                    limit=5, query_text=None):
        from app.config.settings import settings
        await bind_tenant(self.db, user_id)
        embedding_service.validate(query_embedding)
        if not 1 <= limit <= 20:
            raise ValueError('Invalid retrieval limit.')
        await self.db.execute(text("SET LOCAL hnsw.iterative_scan = 'strict_order'"))
        conditions = [DocumentChunk.user_id == user_id,
                      DocumentChunk.embedding.is_not(None),
                      DocumentChunk.embedding_version == embedding_service.version,
                      self._live_source_condition()]
        if source_types:
            conditions.append(DocumentChunk.source_type.in_(source_types))
        # True cosine similarity from PostgreSQL; never invent a confidence score.
        distance = DocumentChunk.embedding.cosine_distance(query_embedding)
        result = await self.db.execute(select(DocumentChunk, distance.label('distance')).where(
            *conditions).order_by(distance).limit(min(limit * 4, 80)))
        vector_rows = [(chunk, 1 - float(dist)) for chunk, dist in result.all()]
        eligible = [(chunk, score) for chunk, score in vector_rows if score >= settings.RAG_MIN_SIMILARITY]
        ranked = {chunk.id: (chunk, score, 1 / (60 + rank))
                  for rank, (chunk, score) in enumerate(eligible, 1)}
        if query_text:
            # Same ACL and embedding-version restrictions apply to both branches.
            terms = func.plainto_tsquery('simple', query_text)
            document = func.to_tsvector('simple', DocumentChunk.content)
            lexical = await self.db.execute(select(DocumentChunk, distance.label('distance')).where(
                *conditions, document.op('@@')(terms)).order_by(
                func.ts_rank_cd(document, terms).desc()).limit(min(limit * 4, 80)))
            for rank, (chunk, dist) in enumerate(lexical.all(), 1):
                previous = ranked.get(chunk.id)
                fusion = (previous[2] if previous else 0) + 1 / (60 + rank)
                ranked[chunk.id] = (chunk, 1 - float(dist), fusion)
        results, seen = [], set()
        for chunk, score, _ in sorted(ranked.values(), key=lambda row: row[2], reverse=True):
            digest = chunk.content_hash
            if digest not in seen:
                results.append((chunk, score))
                seen.add(digest)
            if len(results) == limit:
                break
        return results

    async def create_chat_session(self, user_id, title='New Chat Session'):
        await bind_tenant(self.db, user_id)
        session = ChatSession(user_id=user_id, title=title)
        self.db.add(session)
        await self.db.flush()
        return session

    async def get_user_chat_sessions(self, user_id, limit=50, offset=0):
        await bind_tenant(self.db, user_id)
        result = await self.db.execute(select(ChatSession).where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc(), ChatSession.id).limit(limit).offset(offset))
        return list(result.scalars().all())

    async def get_chat_session(self, session_id, user_id, lock=False):
        await bind_tenant(self.db, user_id)
        stmt = select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
        if lock:
            stmt = stmt.with_for_update()
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_chat_session(self, session_id, user_id):
        await bind_tenant(self.db, user_id)
        result = await self.db.execute(delete(ChatSession).where(
            ChatSession.id == session_id, ChatSession.user_id == user_id))
        return result.rowcount > 0

    async def add_chat_message(self, session_id, user_id, role, content, tokens_used=None, sources_json=None):
        if role not in ('user', 'assistant'):
            raise ValueError('Invalid message role.')
        if not await self.get_chat_session(session_id, user_id):
            raise PermissionError('Session ownership required.')
        msg = ChatMessage(session_id=session_id, user_id=user_id, role=role, content=content,
                          tokens_used=tokens_used, sources_json=sources_json)
        self.db.add(msg)
        await self.db.flush()
        return msg

    async def get_session_messages(self, session_id, user_id, limit=50, exclude_id=None):
        await bind_tenant(self.db, user_id)
        stmt = select(ChatMessage).where(ChatMessage.session_id == session_id, ChatMessage.user_id == user_id)
        if exclude_id:
            stmt = stmt.where(ChatMessage.id != exclude_id)
        result = await self.db.execute(stmt.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(limit))
        return list(reversed(result.scalars().all()))

    async def enqueue_sync(self, user_id):
        await bind_tenant(self.db, user_id)
        await self.db.execute(text('''
            INSERT INTO rag_index_jobs (user_id, revision) VALUES (:uid, 1)
            ON CONFLICT (user_id) DO UPDATE SET revision = rag_index_jobs.revision + 1,
                requested_at = now(), next_attempt_at = now(), attempts = 0, last_error = NULL
        '''), {'uid': user_id})

    async def get_index_revision(self, user_id, lock=False):
        await bind_tenant(self.db, user_id)
        suffix = ' FOR UPDATE' if lock else ''
        result = await self.db.execute(text(
            'SELECT revision FROM rag_index_jobs WHERE user_id = :uid' + suffix), {'uid': user_id})
        return result.scalar_one_or_none()

    async def get_index_status(self, user_id):
        await bind_tenant(self.db, user_id)
        result = await self.db.execute(text('''
            SELECT revision, requested_at, attempts, next_attempt_at, last_error
            FROM rag_index_jobs WHERE user_id = :uid
        '''), {'uid': user_id})
        job = result.mappings().one_or_none()
        count = await self.db.scalar(select(func.count()).select_from(DocumentChunk).where(
            DocumentChunk.user_id == user_id, DocumentChunk.embedding_version == embedding_service.version))
        return {'status': 'pending' if job else 'idle', 'indexed_chunks': count,
                'job': dict(job) if job else None}
