from datetime import datetime
from typing import Optional, List, Dict, Any, Literal, Annotated
import uuid
from pydantic import BaseModel, Field, ConfigDict, StringConstraints

SourceType = Literal['cv', 'project', 'skill', 'cover_letter', 'interview_prep', 'learning']
MessageText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]
TitleText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class DocumentChunkCreate(BaseModel):
    user_id: uuid.UUID
    source_type: SourceType
    source_id: uuid.UUID
    chunk_index: int = Field(default=0, ge=0)
    content: str
    embedding: Optional[List[float]] = None
    metadata_json: Optional[Dict[str, Any]] = None


class DocumentChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    source_type: SourceType
    source_id: uuid.UUID
    chunk_index: int
    content: str
    metadata_json: Optional[Dict[str, Any]] = None
    created_at: datetime


class ChatSessionCreate(BaseModel):
    # Old system_prompt_override is rejected rather than silently accepted.
    model_config = ConfigDict(extra='forbid')
    title: TitleText = 'New Chat Session'


class ChatSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ChatMessageCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    session_id: uuid.UUID
    content: MessageText


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    session_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    content: str
    tokens_used: Optional[int] = None
    sources_json: Optional[List[Dict[str, Any]]] = None
    created_at: datetime
