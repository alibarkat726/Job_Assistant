import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class StructuredInterviewQuestion(BaseModel):
    """Output from the prep agent for a single question."""
    question_text: str = Field(..., description="The interview question text.")
    category: str = Field(..., description="Category of the question: 'technical', 'project', or 'behavioral'.")
    rationale: str = Field(..., description="Explanation of why this question was generated, grounded in the specific input JD skills or projects.")
    suggested_answer_outline: Optional[str] = Field(None, description="Starting point or prompt for the user's answer (not a full script).")


class StructuredInterviewPrepSet(BaseModel):
    """Output from the prep agent for a full set of questions."""
    questions: List[StructuredInterviewQuestion] = Field(..., description="List of generated interview questions.")


# ------------------------------------------------------------------ #
# API Request / Response Schemas
# ------------------------------------------------------------------ #

class InterviewQuestionUpdate(BaseModel):
    """Payload for updating a specific question (e.g. adding notes)."""
    user_notes: Optional[str] = None
    is_practiced: Optional[bool] = None


class InterviewQuestionResponse(BaseModel):
    id: uuid.UUID
    prep_set_id: uuid.UUID
    question_text: str
    category: str
    rationale: str
    suggested_answer_outline: Optional[str]
    user_notes: Optional[str]
    is_practiced: bool
    ordering: int

    class Config:
        from_attributes = True


class InterviewPrepSetResponse(BaseModel):
    id: uuid.UUID
    job_application_id: uuid.UUID
    status: str
    generated_at: Optional[datetime]
    questions: List[InterviewQuestionResponse]

    class Config:
        from_attributes = True
