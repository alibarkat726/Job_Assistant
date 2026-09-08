"""
Unit tests for Dashboard Analytics logic.
Verifies skill gap ranking and learning nudges without hitting the database.
"""
import pytest
from unittest.mock import AsyncMock

from app.dashboard.services import DashboardService
from app.dashboard.schemas import SkillFrequency


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    # Return tuples as expected from the repository: (slug, name, frequency)
    repo.get_missing_skills_frequency.return_value = [
        ("kubernetes", "Kubernetes", 3),
        ("redis", "Redis", 1)
    ]
    repo.get_matched_skills_frequency.return_value = [
        ("python", "Python", 5),
        ("fastapi", "FastAPI", 2)
    ]
    return repo


@pytest.mark.asyncio
async def test_skill_gap_analytics(mock_repo):
    service = DashboardService(repo=mock_repo)
    result = await service.get_skill_gap_analytics()
    
    # Check Missing Skills
    assert len(result.top_missing_skills) == 2
    assert result.top_missing_skills[0].skill_slug == "kubernetes"
    assert result.top_missing_skills[0].frequency_count == 3
    
    # Check Matched Skills
    assert len(result.top_matched_skills) == 2
    assert result.top_matched_skills[0].skill_slug == "python"
    assert result.top_matched_skills[0].frequency_count == 5
    
    # Check Learning Nudge
    assert result.learning_nudge is not None
    assert "Kubernetes" in result.learning_nudge
    assert "3 applications" in result.learning_nudge


@pytest.mark.asyncio
async def test_no_learning_nudge_if_missing_is_rare(mock_repo):
    # Only missing 1 time
    mock_repo.get_missing_skills_frequency.return_value = [
        ("docker", "Docker", 1)
    ]
    service = DashboardService(repo=mock_repo)
    result = await service.get_skill_gap_analytics()
    
    # No nudge if frequency is not > 1
    assert result.learning_nudge is None


@pytest.mark.asyncio
async def test_empty_analytics(mock_repo):
    mock_repo.get_missing_skills_frequency.return_value = []
    mock_repo.get_matched_skills_frequency.return_value = []
    
    service = DashboardService(repo=mock_repo)
    result = await service.get_skill_gap_analytics()
    
    assert len(result.top_missing_skills) == 0
    assert len(result.top_matched_skills) == 0
    assert result.learning_nudge is None
