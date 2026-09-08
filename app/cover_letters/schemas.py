import uuid
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class CoverLetterGenerateRequest(BaseModel):
    tone: str = Field(..., pattern="^(formal|conversational)$", description="Tone of the cover letter.")
    length: str = Field(..., pattern="^(short|standard)$", description="Length of the cover letter.")


class CoverLetterEditRequest(BaseModel):
    content: str = Field(..., description="The edited content of the cover letter draft.")


class CoverLetterResponse(BaseModel):
    id: uuid.UUID
    job_application_id: uuid.UUID
    content: str
    tone: str
    length: str
    status: str
    unverified_claims: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
