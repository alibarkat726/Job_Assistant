import logging
import uuid
from typing import List, Optional
from app.shared.middleware.error_handler import NotFoundError, AppException
from app.core_schema.models import LearningEntry, LearningProposal, ProposedSkillItem
from app.learning.repository import LearningEntryRepository, LearningProposalRepository
from app.skills.repository import SkillRepository
from app.skills.services import SkillsService
from app.learning.schemas import (
    LearningEntryCreate,
    LearningEntryUpdate,
    LearningEntryResponse,
    LearningProposalResponse,
    ProposedSkillItemResponse,
    ProposalApprovalRequest
)
from app.learning.triage_agent import ITriageAgent

logger = logging.getLogger(__name__)


class LearningService:
    """
    Service layer for Daily Learning Log CRUD and Triage Agent coordination.
    """

    def __init__(
        self,
        entry_repo: LearningEntryRepository,
        proposal_repo: LearningProposalRepository,
        skill_repo: SkillRepository,
        skills_service: SkillsService,
        triage_agent: ITriageAgent,
    ):
        self.entry_repo = entry_repo
        self.proposal_repo = proposal_repo
        self.skill_repo = skill_repo
        self.skills_service = skills_service
        self.triage_agent = triage_agent

    # ------------------------------------------------------------------ #
    # Learning Entry CRUD
    # ------------------------------------------------------------------ #

    async def create_entry(self, dto: LearningEntryCreate) -> LearningEntryResponse:
        """
        Create a new learning entry, then asynchronously run the triage agent
        to generate a proposal.
        """
        entry = LearningEntry(
            title=dto.title,
            content=dto.content,
            timestamp=dto.timestamp
        )
        created = await self.entry_repo.create(entry)
        
        # Run Triage Agent synchronously for now (could be dispatched to background)
        await self._run_triage_for_entry(created)
        
        return self._map_entry_to_response(created)

    async def get_entry(self, entry_id: uuid.UUID) -> LearningEntryResponse:
        entry = await self.entry_repo.get_by_id(entry_id)
        if not entry:
            raise NotFoundError(f"Learning entry '{entry_id}' not found.")
        return self._map_entry_to_response(entry)

    async def list_entries(self) -> List[LearningEntryResponse]:
        entries = await self.entry_repo.find_all()
        return [self._map_entry_to_response(e) for e in entries]

    async def update_entry(self, entry_id: uuid.UUID, dto: LearningEntryUpdate) -> LearningEntryResponse:
        entry = await self.entry_repo.get_by_id(entry_id)
        if not entry:
            raise NotFoundError(f"Learning entry '{entry_id}' not found.")
        
        if dto.title is not None:
            entry.title = dto.title
        if dto.content is not None:
            entry.content = dto.content
        if dto.timestamp is not None:
            entry.timestamp = dto.timestamp
            
        updated = await self.entry_repo.update(entry)
        return self._map_entry_to_response(updated)

    async def delete_entry(self, entry_id: uuid.UUID) -> None:
        entry = await self.entry_repo.get_by_id(entry_id)
        if not entry:
            raise NotFoundError(f"Learning entry '{entry_id}' not found.")
        await self.entry_repo.delete(entry)

    # ------------------------------------------------------------------ #
    # Triage Agent Orchestration
    # ------------------------------------------------------------------ #

    async def _run_triage_for_entry(self, entry: LearningEntry) -> None:
        """
        Execute the Triage Agent and save the resulting proposal.
        """
        existing_skills = await self.skill_repo.find_all()
        
        try:
            triage_output = await self.triage_agent.classify_entry(entry.content, existing_skills)
            
            proposal = LearningProposal(
                entry_id=entry.id,
                user_id=entry.user_id,
                is_skill_worthy=triage_output.is_skill_worthy,
                reasoning=triage_output.reasoning,
                status="pending"
            )
            created_proposal = await self.proposal_repo.create(proposal)
            
            # Note: We must flush to get proposal.id, but BaseTenantRepository.create does session.commit()
            
            # Now insert child items manually since create() committed the parent.
            # Using repo.db for direct session access.
            for ps in triage_output.proposed_skills:
                item = ProposedSkillItem(
                    proposal_id=created_proposal.id,
                    user_id=entry.user_id,
                    skill_name=ps.skill_name,
                    action=ps.action,
                    matched_skill_id=ps.matched_skill_id,
                    confidence=ps.confidence,
                    status="pending"
                )
                self.proposal_repo.db.add(item)
            await self.proposal_repo.db.commit()
            
        except Exception as e:
            logger.error(f"Triage agent failed for entry {entry.id}: {e}")
            # On failure, create a proposal marked needs_manual_review
            proposal = LearningProposal(
                entry_id=entry.id,
                user_id=entry.user_id,
                is_skill_worthy=False,
                reasoning=f"Agent failed to parse entry: {str(e)}",
                status="needs_manual_review"
            )
            await self.proposal_repo.create(proposal)


    # ------------------------------------------------------------------ #
    # Approval Flow
    # ------------------------------------------------------------------ #

    async def list_pending_proposals(self) -> List[LearningProposalResponse]:
        proposals = await self.proposal_repo.find_pending_with_items()
        return [self._map_proposal_to_response(p) for p in proposals]

    async def get_proposal(self, proposal_id: uuid.UUID) -> LearningProposalResponse:
        proposal = await self.proposal_repo.get_with_items(proposal_id)
        if not proposal:
            raise NotFoundError(f"Proposal '{proposal_id}' not found.")
        return self._map_proposal_to_response(proposal)

    async def approve_proposal(self, proposal_id: uuid.UUID, dto: ProposalApprovalRequest) -> LearningProposalResponse:
        """
        Approve a proposal. The DTO specifies which proposed items to accept.
        Accepted items mutate the canonical profile via SkillsService.
        """
        proposal = await self.proposal_repo.get_with_items(proposal_id)
        if not proposal:
            raise NotFoundError(f"Proposal '{proposal_id}' not found.")
        
        if proposal.status != "pending" and proposal.status != "needs_manual_review":
            raise AppException("Proposal is already processed.", "PROPOSAL_PROCESSED", 400)

        # Process each item
        approved_ids = set(dto.approved_item_ids)
        for item in proposal.proposed_skills:
            if item.id in approved_ids:
                item.status = "approved"
                
                # Apply mutations to the skill graph
                if item.action == "create_new":
                    # New skills always start at proficiency 1, regardless of agent confidence
                    await self.skills_service.upsert_skill(
                        name=item.skill_name,
                        source="learning",
                        proficiency=1
                    )
                elif item.action == "reinforce_existing" and item.matched_skill_id:
                    # Fetch existing skill to increment proficiency
                    existing_skill = await self.skill_repo.get_by_id(item.matched_skill_id)
                    if existing_skill:
                        new_prof = min(5, existing_skill.proficiency + 1)
                        await self.skills_service.upsert_skill(
                            name=existing_skill.name, # use original name to avoid changing slug accidentally
                            source="learning",
                            proficiency=new_prof
                        )
            else:
                item.status = "rejected"

        proposal.status = "approved"
        
        updated = await self.proposal_repo.update(proposal)
        # re-fetch to ensure relations are updated
        refreshed = await self.proposal_repo.get_with_items(updated.id)
        return self._map_proposal_to_response(refreshed)

    async def reject_proposal(self, proposal_id: uuid.UUID) -> LearningProposalResponse:
        """Reject a proposal entirely."""
        proposal = await self.proposal_repo.get_with_items(proposal_id)
        if not proposal:
            raise NotFoundError(f"Proposal '{proposal_id}' not found.")
        
        if proposal.status != "pending" and proposal.status != "needs_manual_review":
            raise AppException("Proposal is already processed.", "PROPOSAL_PROCESSED", 400)

        proposal.status = "rejected"
        for item in proposal.proposed_skills:
            item.status = "rejected"

        updated = await self.proposal_repo.update(proposal)
        refreshed = await self.proposal_repo.get_with_items(updated.id)
        return self._map_proposal_to_response(refreshed)


    # ------------------------------------------------------------------ #
    # Mapping
    # ------------------------------------------------------------------ #

    def _map_entry_to_response(self, entry: LearningEntry) -> LearningEntryResponse:
        return LearningEntryResponse(
            id=entry.id,
            user_id=entry.user_id,
            title=entry.title,
            content=entry.content,
            timestamp=entry.timestamp,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )

    def _map_proposal_to_response(self, proposal: LearningProposal) -> LearningProposalResponse:
        items = []
        if proposal.proposed_skills:
            for item in proposal.proposed_skills:
                items.append(ProposedSkillItemResponse(
                    id=item.id,
                    proposal_id=item.proposal_id,
                    skill_name=item.skill_name,
                    action=item.action,
                    matched_skill_id=item.matched_skill_id,
                    confidence=item.confidence,
                    status=item.status
                ))
                
        return LearningProposalResponse(
            id=proposal.id,
            entry_id=proposal.entry_id,
            is_skill_worthy=proposal.is_skill_worthy,
            reasoning=proposal.reasoning,
            status=proposal.status,
            proposed_skills=items,
            created_at=proposal.created_at,
            updated_at=proposal.updated_at,
        )
