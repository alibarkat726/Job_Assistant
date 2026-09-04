import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.learning.services import LearningService
from app.learning.schemas import LearningEntryCreate, ProposalApprovalRequest
from app.learning.triage_agent import TriageProposalOutput, TriageProposedSkill
from app.core_schema.models import LearningEntry, LearningProposal, ProposedSkillItem, Skill
from app.shared.middleware.error_handler import AppException

@pytest.fixture
def mock_repos():
    entry_repo = MagicMock()
    entry_repo.create = AsyncMock(side_effect=lambda x: _set_id(x))
    entry_repo.get_by_id = AsyncMock()
    
    proposal_repo = MagicMock()
    proposal_repo.create = AsyncMock(side_effect=lambda x: _set_id(x))
    proposal_repo.get_with_items = AsyncMock()
    proposal_repo.update = AsyncMock(side_effect=lambda x: x)
    proposal_repo.db = MagicMock()
    proposal_repo.db.add = MagicMock()
    proposal_repo.db.commit = AsyncMock()
    
    skill_repo = MagicMock()
    skill_repo.find_all = AsyncMock(return_value=[])
    skill_repo.get_by_id = AsyncMock()
    
    skills_service = MagicMock()
    skills_service.upsert_skill = AsyncMock()
    
    triage_agent = MagicMock()
    triage_agent.classify_entry = AsyncMock()
    
    return {
        "entry_repo": entry_repo,
        "proposal_repo": proposal_repo,
        "skill_repo": skill_repo,
        "skills_service": skills_service,
        "triage_agent": triage_agent
    }

def _set_id(model):
    model.id = uuid.uuid4()
    model.user_id = uuid.uuid4()
    from datetime import datetime, timezone
    model.created_at = datetime.now(timezone.utc)
    model.updated_at = datetime.now(timezone.utc)
    return model

@pytest.mark.asyncio
async def test_create_entry_triggers_triage(mock_repos):
    triage_output = TriageProposalOutput(
        is_skill_worthy=True,
        reasoning="Test reasoning",
        proposed_skills=[
            TriageProposedSkill(skill_name="Python", action="create_new", confidence="high")
        ]
    )
    mock_repos["triage_agent"].classify_entry.return_value = triage_output
    
    service = LearningService(**mock_repos)
    dto = LearningEntryCreate(title="Test", content="I learned Python")
    
    result = await service.create_entry(dto)
    
    assert result.content == "I learned Python"
    mock_repos["triage_agent"].classify_entry.assert_called_once()
    mock_repos["proposal_repo"].create.assert_called_once()
    mock_repos["proposal_repo"].db.add.assert_called_once()


@pytest.mark.asyncio
async def test_approve_proposal_mutates_skills(mock_repos):
    service = LearningService(**mock_repos)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    proposal = LearningProposal(id=uuid.uuid4(), entry_id=uuid.uuid4(), status="pending", is_skill_worthy=True, created_at=now, updated_at=now)
    item1 = ProposedSkillItem(id=uuid.uuid4(), proposal_id=proposal.id, skill_name="FastAPI", action="create_new", confidence="high", status="pending")
    item2 = ProposedSkillItem(id=uuid.uuid4(), proposal_id=proposal.id, skill_name="Python", action="reinforce_existing", matched_skill_id=uuid.uuid4(), confidence="high", status="pending")
    proposal.proposed_skills = [item1, item2]
    
    mock_repos["proposal_repo"].get_with_items.return_value = proposal
    
    existing_skill = Skill(name="Python", proficiency=3)
    mock_repos["skill_repo"].get_by_id.return_value = existing_skill
    
    dto = ProposalApprovalRequest(approved_item_ids=[item1.id, item2.id])
    await service.approve_proposal(proposal.id, dto)
    
    assert item1.status == "approved"
    assert item2.status == "approved"
    assert proposal.status == "approved"
    
    assert mock_repos["skills_service"].upsert_skill.call_count == 2
    mock_repos["skills_service"].upsert_skill.assert_any_call(
        name="FastAPI", source="learning", proficiency=1
    )
    mock_repos["skills_service"].upsert_skill.assert_any_call(
        name="Python", source="learning", proficiency=4
    )

@pytest.mark.asyncio
async def test_partial_approval_rejects_unlisted_items(mock_repos):
    service = LearningService(**mock_repos)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    proposal = LearningProposal(id=uuid.uuid4(), entry_id=uuid.uuid4(), status="pending", is_skill_worthy=True, created_at=now, updated_at=now)
    item1 = ProposedSkillItem(id=uuid.uuid4(), proposal_id=proposal.id, skill_name="FastAPI", action="create_new", confidence="high", status="pending")
    item2 = ProposedSkillItem(id=uuid.uuid4(), proposal_id=proposal.id, skill_name="BadSkill", action="create_new", confidence="low", status="pending")
    proposal.proposed_skills = [item1, item2]
    
    mock_repos["proposal_repo"].get_with_items.return_value = proposal
    
    dto = ProposalApprovalRequest(approved_item_ids=[item1.id])
    await service.approve_proposal(proposal.id, dto)
    
    assert item1.status == "approved"
    assert item2.status == "rejected"
    assert proposal.status == "approved"
    
    mock_repos["skills_service"].upsert_skill.assert_called_once_with(
        name="FastAPI", source="learning", proficiency=1
    )

@pytest.mark.asyncio
async def test_reject_proposal(mock_repos):
    service = LearningService(**mock_repos)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    proposal = LearningProposal(id=uuid.uuid4(), entry_id=uuid.uuid4(), status="pending", is_skill_worthy=True, created_at=now, updated_at=now)
    item1 = ProposedSkillItem(id=uuid.uuid4(), proposal_id=proposal.id, skill_name="FastAPI", action="create_new", confidence="high", status="pending")
    proposal.proposed_skills = [item1]
    
    mock_repos["proposal_repo"].get_with_items.return_value = proposal
    
    await service.reject_proposal(proposal.id)
    
    assert proposal.status == "rejected"
    assert item1.status == "rejected"
    mock_repos["skills_service"].upsert_skill.assert_not_called()
