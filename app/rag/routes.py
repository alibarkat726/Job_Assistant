import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.users.models import User
from app.shared.db.session import get_db
from app.shared.middleware.rate_limiter import limiter, authenticated_rate_key
from app.config.settings import settings
from app.rag.schemas import ChatSessionCreate, ChatSessionRead, ChatMessageCreate, ChatMessageRead, SourceType
from app.rag.repository import RAGRepository
from app.rag.services import RAGChatService
from app.rag.embedding import ProviderUnavailable
from app.rag.quota import TokenBudgetExceeded

router = APIRouter(prefix='/api/v1/chat', tags=['RAG Chatbot'])


@router.post('/sessions', response_model=ChatSessionRead, status_code=201)
@limiter.limit(settings.RAG_CHAT_RATE_LIMIT, key_func=authenticated_rate_key)
async def create_chat_session(request: Request, dto: ChatSessionCreate,
                              current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    session = await RAGRepository(db).create_chat_session(current_user.id, dto.title)
    return ChatSessionRead.model_validate(session)


@router.get('/sessions', response_model=list[ChatSessionRead])
async def list_chat_sessions(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                             current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    sessions = await RAGRepository(db).get_user_chat_sessions(current_user.id, limit, offset)
    return [ChatSessionRead.model_validate(session) for session in sessions]


@router.get('/sessions/{session_id}/messages', response_model=list[ChatMessageRead])
async def get_session_messages(session_id: uuid.UUID, limit: int = Query(50, ge=1, le=200),
                               current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    repo = RAGRepository(db)
    if not await repo.get_chat_session(session_id, current_user.id):
        raise HTTPException(404, 'Chat session not found.')
    return [ChatMessageRead.model_validate(msg) for msg in
            await repo.get_session_messages(session_id, current_user.id, limit)]


@router.delete('/sessions/{session_id}', status_code=204)
async def delete_chat_session(session_id: uuid.UUID, current_user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    if not await RAGRepository(db).delete_chat_session(session_id, current_user.id):
        raise HTTPException(404, 'Chat session not found.')


@router.post('/messages', response_model=ChatMessageRead)
@limiter.limit(settings.RAG_CHAT_RATE_LIMIT, key_func=authenticated_rate_key)
async def send_chat_message(request: Request, dto: ChatMessageCreate,
                            source_types: Optional[list[SourceType]] = Query(None),
                            top_k: int = Query(5, ge=1, le=20),
                            current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        return await RAGChatService(db).send_message(current_user.id, dto.session_id, dto.content, source_types, top_k)
    except ProviderUnavailable:
        raise HTTPException(503, 'AI service temporarily unavailable. Please retry.') from None
    except TokenBudgetExceeded:
        raise HTTPException(429, 'Daily AI token budget exhausted. Please retry tomorrow.') from None
    # Domain errors and unexpected failures are handled centrally, without exposing SDK details.


@router.post('/ingest/sync-all', status_code=202)
@limiter.limit(settings.RAG_SYNC_RATE_LIMIT, key_func=authenticated_rate_key)
async def sync_user_vector_data(request: Request, current_user: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    await RAGRepository(db).enqueue_sync(current_user.id)
    return {'status': 'queued', 'message': 'Indexing requested. Check /api/v1/chat/ingest/status for progress.'}


@router.get('/ingest/status')
async def index_status(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await RAGRepository(db).get_index_status(current_user.id)
