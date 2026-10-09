"""Tenant-owned, token-bounded ingestion with atomic index replacement."""
import hashlib
import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config.settings import settings
from app.core_schema.models import CV, Project, Skill, CoverLetter, InterviewPrepSet, LearningEntry
from app.rag.models import DocumentChunk
from app.rag.repository import RAGRepository
from app.rag.embedding import embedding_service
from app.rag.tokens import count_tokens
from app.rag.quota import reserve_tokens
from app.shared.db.tenant import bind_tenant

CHUNKING_VERSION = 'sections-tokens-v1'
SOURCES = {'cv': CV, 'project': Project, 'skill': Skill, 'cover_letter': CoverLetter,
           'interview_prep': InterviewPrepSet, 'learning': LearningEntry}


class RAGIngestionService:
    def __init__(self, db):
        self.db = db
        self.repo = RAGRepository(db)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.RAG_CHUNK_TOKENS,
            chunk_overlap=settings.RAG_CHUNK_OVERLAP_TOKENS,
            length_function=count_tokens, separators=['\n\n', '\n', ' ', ''])

    def _assert_owner(self, user_id, entity):
        if entity.user_id != user_id:
            raise PermissionError('Source does not belong to the authenticated user.')

    async def ingest_cv(self, user_id, cv):
        self._assert_owner(user_id, cv)
        items = [(f'CV: {cv.title}\nName: {cv.full_name or ""}\nSummary: {cv.summary or ""}',
                  {'section': 'summary'})]
        for work in cv.work_histories:
            items.append((f'Work experience: {work.company}\nRole: {work.role}\nDates: {work.start_date or ""} - {work.end_date or "Present"}\n{work.description or ""}',
                          {'section': 'work_history', 'entry_id': str(work.id)}))
        for edu in cv.education_entries:
            items.append((f'Education: {edu.degree or ""} in {edu.field_of_study or ""} at {edu.institution}\nDates: {edu.start_date or ""} - {edu.end_date or ""}',
                          {'section': 'education', 'entry_id': str(edu.id)}))
        if cv.skills:
            items.append(('CV skills: ' + ', '.join(skill.name for skill in cv.skills), {'section': 'skills'}))
        # Preserve extraction information even when the parser found some fields.
        if cv.raw_text:
            items.append((cv.raw_text, {'section': 'raw_text'}))
        return await self._store_chunks(user_id, 'cv', cv.id, items)

    async def ingest_project(self, user_id, project):
        self._assert_owner(user_id, project)
        skills = ', '.join(link.skill.name for link in project.project_skills)
        content = f'Project: {project.title}\nDates: {project.start_date or ""} - {project.end_date or ""}\nSkills: {skills}\n{project.description or ""}'
        return await self._store_chunks(user_id, 'project', project.id,
            [(content, {'title': project.title, 'urls': project.urls or []})])

    async def ingest_skill(self, user_id, skill):
        self._assert_owner(user_id, skill)
        content = f'Skill: {skill.name}\nCategory: {skill.category or "General"}\nProficiency: {skill.proficiency}/5'
        return await self._store_chunks(user_id, 'skill', skill.id, [(content, {'name': skill.name})])

    async def ingest_cover_letter(self, user_id, letter):
        self._assert_owner(user_id, letter)
        return await self._store_chunks(user_id, 'cover_letter', letter.id,
            [(f'Generated cover letter: {letter.content or ""}', {'generated': True, 'tone': letter.tone})])

    async def ingest_interview_prep(self, user_id, prep):
        self._assert_owner(user_id, prep)
        items = [(f'Interview question ({q.category}): {q.question_text}\nSuggested outline: {q.suggested_answer_outline or ""}\nUser notes: {q.user_notes or ""}',
                  {'question_id': str(q.id), 'generated': True}) for q in prep.questions]
        return await self._store_chunks(user_id, 'interview_prep', prep.id, items)

    async def ingest_learning(self, user_id, entry):
        self._assert_owner(user_id, entry)
        return await self._store_chunks(user_id, 'learning', entry.id,
            [(f'Learning: {entry.title or ""}\n{entry.content}', {'section': 'learning'})])

    async def sync_all_user_data(self, user_id) -> int:
        await bind_tenant(self.db, user_id)
        # Serialize all index writers for this user until the caller commits.
        await self.db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'),
                              {'key': f'rag:{user_id}'})
        # Read a coherent source snapshot; conflicting mutations must not publish stale chunks.
        revision = await self.repo.get_index_revision(user_id)
        total = 0
        for source_type, model in SOURCES.items():
            stmt = select(model).where(model.user_id == user_id)
            if model is InterviewPrepSet:
                stmt = stmt.options(selectinload(InterviewPrepSet.questions))
            elif model is Project:
                from app.core_schema.models import ProjectSkill
                stmt = stmt.options(selectinload(Project.project_skills).selectinload(ProjectSkill.skill))
            result = await self.db.execute(stmt)
            for entity in result.scalars().all():
                chunks = await getattr(self, f'ingest_{source_type}')(user_id, entity)
                total += len(chunks)
        # Outbox revision check uses a row lock: writers either finish before this check,
        # or invalidate the new index after this transaction commits.
        if await self.repo.get_index_revision(user_id, lock=True) != revision:
            raise IndexChanged('Source data changed during indexing; retry required.')
        await self.repo.prune_deleted_sources(user_id)
        return total

    async def _store_chunks(self, user_id, source_type, source_id, items):
        parts = []
        for section_index, (content, metadata) in enumerate(items):
            for part_index, part in enumerate(self.text_splitter.split_text(content)):
                if part.strip():
                    parts.append((part, {**metadata, 'section_index': section_index,
                                         'part_index': part_index, 'token_count': count_tokens(part)}))
        hashes = [hashlib.sha256(content.encode()).hexdigest() for content, _ in parts]
        existing = await self.repo.get_source_chunks(user_id, source_type, source_id)
        if len(existing) == len(parts) and all(
            chunk.content_hash == digest and chunk.embedding_version == embedding_service.version
            and chunk.chunking_version == CHUNKING_VERSION and chunk.metadata_json == metadata
            for chunk, digest, (_, metadata) in zip(existing, hashes, parts)):
            return existing
        await reserve_tokens(user_id, sum(count_tokens(part) for part, _ in parts))
        embeddings = await embedding_service.generate_batch_embeddings([part for part, _ in parts])
        chunks = [DocumentChunk(user_id=user_id, source_type=source_type, source_id=source_id,
            chunk_index=index, content=content, embedding=vector,
            embedding_version=embedding_service.version, chunking_version=CHUNKING_VERSION,
            content_hash=hashlib.sha256(content.encode()).hexdigest(), metadata_json=metadata)
            for index, ((content, metadata), vector) in enumerate(zip(parts, embeddings))]
        # No deletes occur until every replacement embedding has succeeded.
        await self.repo.replace_source_chunks(user_id, source_type, source_id, chunks)
        return chunks


class IndexChanged(RuntimeError):
    pass
