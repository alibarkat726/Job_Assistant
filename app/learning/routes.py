import uuid
from typing import List
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.db.session import get_db
from app.users.models import User
from app.auth.dependencies import get_current_user
from app.skills.repository import SkillRepository
from app.skills.services import SkillsService
from app.learning.repository import LearningEntryRepository, LearningProposalRepository
from app.learning.services import LearningService
from app.learning.triage_agent import HeuristicTriageAgent
from app.learning.schemas import (
    LearningEntryCreate,
    LearningEntryUpdate,
    LearningEntryResponse,
    LearningProposalResponse,
    ProposalApprovalRequest
)
import bleach

router = APIRouter(prefix="/api/v1/learning", tags=["Learning Log"])


async def get_learning_service(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LearningService:
    """Dependency: tenant-scoped LearningService."""
    entry_repo = LearningEntryRepository(db=db, tenant_id=current_user.id)
    proposal_repo = LearningProposalRepository(db=db, tenant_id=current_user.id)
    skill_repo = SkillRepository(db=db, tenant_id=current_user.id)
    skills_service = SkillsService(skill_repo=skill_repo)
    triage_agent = HeuristicTriageAgent() # Using heuristic agent for now
    
    return LearningService(
        entry_repo=entry_repo,
        proposal_repo=proposal_repo,
        skill_repo=skill_repo,
        skills_service=skills_service,
        triage_agent=triage_agent
    )


# ------------------------------------------------------------------ #
# Learning Entry Routes
# ------------------------------------------------------------------ #

@router.post("", response_model=LearningEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_learning_entry(
    dto: LearningEntryCreate,
    learning_service: LearningService = Depends(get_learning_service),
):
    """
    Log a new learning entry.
    Automatically triggers the Triage Agent in the background to generate a proposal.
    """
    # Sanitize content before creating
    dto.content = bleach.clean(dto.content, strip=True)
    if dto.title:
        dto.title = bleach.clean(dto.title, strip=True)
        
    return await learning_service.create_entry(dto)


@router.get("", response_model=List[LearningEntryResponse])
async def list_learning_entries(
    learning_service: LearningService = Depends(get_learning_service),
):
    """List all learning entries for the user."""
    return await learning_service.list_entries()


@router.get("/{entry_id}", response_model=LearningEntryResponse)
async def get_learning_entry(
    entry_id: uuid.UUID,
    learning_service: LearningService = Depends(get_learning_service),
):
    """Get a single learning entry."""
    return await learning_service.get_entry(entry_id)


@router.put("/{entry_id}", response_model=LearningEntryResponse)
async def update_learning_entry(
    entry_id: uuid.UUID,
    dto: LearningEntryUpdate,
    learning_service: LearningService = Depends(get_learning_service),
):
    """Update a learning entry."""
    if dto.content:
        dto.content = bleach.clean(dto.content, strip=True)
    if dto.title:
        dto.title = bleach.clean(dto.title, strip=True)
        
    return await learning_service.update_entry(entry_id, dto)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_learning_entry(
    entry_id: uuid.UUID,
    learning_service: LearningService = Depends(get_learning_service),
):
    """Delete a learning entry and its associated proposals."""
    await learning_service.delete_entry(entry_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ #
# Learning Proposal Routes
# ------------------------------------------------------------------ #

@router.get("/proposals/pending", response_model=List[LearningProposalResponse])
async def list_pending_proposals(
    learning_service: LearningService = Depends(get_learning_service),
):
    """List all pending learning proposals awaiting human review."""
    return await learning_service.list_pending_proposals()


@router.get("/proposals/{proposal_id}", response_model=LearningProposalResponse)
async def get_proposal(
    proposal_id: uuid.UUID,
    learning_service: LearningService = Depends(get_learning_service),
):
    """Get a specific proposal by ID."""
    return await learning_service.get_proposal(proposal_id)


@router.post("/proposals/{proposal_id}/approve", response_model=LearningProposalResponse)
async def approve_proposal(
    proposal_id: uuid.UUID,
    dto: ProposalApprovalRequest,
    learning_service: LearningService = Depends(get_learning_service),
):
    """
    Approve a proposal (partially or fully). 
    Requires an array of approved_item_ids representing the skills to accept.
    Mutates the canonical profile.
    """
    return await learning_service.approve_proposal(proposal_id, dto)


@router.post("/proposals/{proposal_id}/reject", response_model=LearningProposalResponse)
async def reject_proposal(
    proposal_id: uuid.UUID,
    learning_service: LearningService = Depends(get_learning_service),
):
    """Reject a proposal outright."""
    return await learning_service.reject_proposal(proposal_id)
