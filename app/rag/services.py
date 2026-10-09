import logging
import time

from langchain_core.messages import HumanMessage, AIMessage
from app.config.settings import settings
from app.shared.middleware.error_handler import NotFoundError
from app.rag.repository import RAGRepository
from app.rag.schemas import ChatMessageRead
from app.rag.graph import rag_graph
from app.rag.tokens import count_tokens
from app.rag.quota import reserve_tokens

logger = logging.getLogger(__name__)


class RAGChatService:
    def __init__(self, db):
        self.db = db
        self.repo = RAGRepository(db)

    async def send_message(self, user_id, session_id, user_content, source_types=None, top_k=5):
        started = time.monotonic()
        # Serialize turns so parallel requests cannot interleave conversation history.
        session = await self.repo.get_chat_session(session_id, user_id, lock=True)
        if not session:
            raise NotFoundError('Chat session not found.')
        # Reserve the upper bound before any embedding or generation request.
        await reserve_tokens(user_id, settings.RAG_CONTEXT_TOKENS + settings.RAG_HISTORY_TOKENS
            + settings.RAG_OUTPUT_TOKENS + 2 * count_tokens(user_content) + 1000)
        user_msg = await self.repo.add_chat_message(session_id, user_id, 'user', user_content)
        past = await self.repo.get_session_messages(session_id, user_id, limit=20, exclude_id=user_msg.id)
        history, budget = [], settings.RAG_HISTORY_TOKENS
        for message in reversed(past):
            size = count_tokens(message.content) + 4
            if size > budget:
                break
            cls = AIMessage if message.role == 'assistant' else HumanMessage
            history.append(cls(content=message.content))
            budget -= size
        result = await rag_graph.ainvoke({'user_id': user_id, 'session_id': session_id,
            'user_content': user_content, 'source_types': source_types, 'top_k': top_k,
            'db': self.db, 'chat_history': list(reversed(history))})
        response = await self.repo.add_chat_message(session_id, user_id, 'assistant',
            result['generation'], tokens_used=result.get('tokens_used'), sources_json=result.get('citations', []))
        from datetime import datetime, timezone
        session.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        logger.info('rag_chat_completed duration_ms=%d sources=%d tokens=%s',
            int((time.monotonic() - started) * 1000), len(result.get('citations', [])), result.get('tokens_used'))
        return ChatMessageRead.model_validate(response)
