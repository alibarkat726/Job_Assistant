from datetime import datetime
from typing import List, Literal, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


# ------------------------------------------------------------------ #
# Learning Entry Schemas
# ------------------------------------------------------------------ #

class LearningEntryCreate(BaseModel):
    """Request schema for logging a new learning entry."""
    title: Optional[str] = Field(None, max_length=255)
    content: str = Field(..., min_length=1, max_length=10000)
    timestamp: Optional[datetime] = Field(default_factory=lambda: datetime.now())

    @field_validator("content")
    @classmethod
    def strip_content(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Content cannot be blank.")
        return stripped


class LearningEntryUpdate(BaseModel):
    """Request schema for updating a learning entry."""
    title: Optional[str] = Field(None, max_length=255)
    content: Optional[str] = Field(None, min_length=1, max_length=10000)
    timestamp: Optional[datetime] = None


class LearningEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    user_id: uuid.UUID
    title: Optional[str] = None
    content: str
    timestamp: datetime
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------ #
# Proposal & Triage Schemas
# ------------------------------------------------------------------ #

ActionType = Literal["reinforce_existing", "create_new"]
ConfidenceType = Literal["high", "medium", "low"]
StatusType = Literal["pending", "approved", "rejected", "needs_manual_review"]

class ProposedSkillItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    proposal_id: uuid.UUID
    skill_name: str
    action: ActionType
    matched_skill_id: Optional[uuid.UUID] = None
    confidence: ConfidenceType
    status: StatusType


class LearningProposalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    entry_id: uuid.UUID
    is_skill_worthy: bool
    reasoning: Optional[str] = None
    status: StatusType
    proposed_skills: List[ProposedSkillItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class TriageProposedSkill(BaseModel):
    """Internal model for the TriageAgent output before DB persistence."""
    skill_name: str
    action: ActionType
    matched_skill_id: Optional[uuid.UUID] = None
    confidence: ConfidenceType


class TriageProposalOutput(BaseModel):
    """Internal model for the TriageAgent output before DB persistence."""
    is_skill_worthy: bool
    reasoning: Optional[str] = None
    proposed_skills: List[TriageProposedSkill] = Field(default_factory=list)


# ------------------------------------------------------------------ #
# Approval Schemas
# ------------------------------------------------------------------ #

class ProposalApprovalRequest(BaseModel):
    """Request to approve a proposal. Can be partial."""
    approved_item_ids: List[uuid.UUID] = Field(
        default_factory=list, 
        description="List of proposed_skill_items IDs to approve. If empty, the proposal is marked approved but no skills are modified."
    )
