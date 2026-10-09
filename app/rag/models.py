from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import uuid
from sqlalchemy import String, Integer, BigInteger, Text, ForeignKey, ForeignKeyConstraint, DateTime, JSON, Index, UniqueConstraint, CheckConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from app.shared.db.base import Base, TimestampMixin


class DocumentChunk(Base, TimestampMixin):
    """
    Stores text chunks and vector embeddings of user domain data (CVs, Projects, Skills,
    Cover Letters, Interview Preps, Learning Entries) for production RAG retrieval.
    Enforces strict multi-tenant isolation via user_id foreign key and Row-Level Security.
    """
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # 'cv', 'project', 'skill', 'cover_letter', 'interview_prep', 'learning'
    source_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False, index=True
    )  # Entity UUID in its original table
    chunk_index: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(768), nullable=True
    )
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True, default=dict
    )
    embedding_version: Mapped[str] = mapped_column(String(255), nullable=False)
    chunking_version: Mapped[str] = mapped_column(String(100), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        Index("ix_document_chunks_user_source", "user_id", "source_type"),
        UniqueConstraint("user_id", "source_type", "source_id", "chunk_index", name="uq_document_chunks_source_position"),
        CheckConstraint("chunk_index >= 0", name="chunk_index_nonnegative"),
    )


class ChatSession(Base, TimestampMixin):
    """
    Represents a conversational session between a user and the RAG Chatbot agent.
    """
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(
        String(255), nullable=False, default="New Chat Session"
    )
    messages: Mapped[List["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan", foreign_keys="ChatMessage.session_id"
    )
    user: Mapped["User"] = relationship("User")
    __table_args__ = (UniqueConstraint("id", "user_id", name="uq_chat_sessions_id_user"),)


class ChatMessage(Base):
    """
    Individual chat messages stored in a ChatSession, including citations and usage metrics.
    """
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'user', 'assistant', 'system'
    content: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    tokens_used: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    sources_json: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON, nullable=True
    )  # Retrieved chunks/citations used for generating this response
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages", foreign_keys=[session_id])
    user: Mapped["User"] = relationship("User")
    __table_args__ = (
        ForeignKeyConstraint(["session_id", "user_id"], ["chat_sessions.id", "chat_sessions.user_id"],
                             name="fk_chat_messages_session_owner", ondelete="CASCADE"),
        CheckConstraint("role IN ('user', 'assistant')", name="message_role"),
        Index("ix_chat_messages_user_session_created", "user_id", "session_id", "created_at"),
    )


class RAGIndexJob(Base):
    __tablename__ = "rag_index_jobs"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="1")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_error: Mapped[Optional[str]] = mapped_column(String(100))
    __table_args__ = (Index("ix_rag_index_jobs_due", "next_attempt_at"),)
