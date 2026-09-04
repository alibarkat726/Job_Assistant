"""
Unit tests for SkillsService and normalize_skill_name.

These tests use mock repositories to isolate service logic without hitting the database.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.skills.services import SkillsService, normalize_skill_name
from app.skills.schemas import SkillCreate, SkillUpdate
from app.core_schema.models import Skill
from app.shared.middleware.error_handler import NotFoundError, AppException


# ------------------------------------------------------------------ #
# normalize_skill_name
# ------------------------------------------------------------------ #

class TestNormalizeSkillName:
    def test_lowercase_conversion(self):
        assert normalize_skill_name("React") == "react"

    def test_strips_whitespace(self):
        assert normalize_skill_name("  Python  ") == "python"

    def test_collapses_internal_whitespace(self):
        assert normalize_skill_name("Node  JS") == "node js"

    def test_preserves_special_chars(self):
        assert normalize_skill_name("C++") == "c++"
        assert normalize_skill_name("React.js") == "react.js"

    def test_mixed_case_and_spaces(self):
        assert normalize_skill_name("  TypeScript  ") == "typescript"

    def test_identical_slugs_from_variants(self):
        assert normalize_skill_name("React") == normalize_skill_name("react") == normalize_skill_name("REACT")


# ------------------------------------------------------------------ #
# Helper — build a mock Skill ORM object
# ------------------------------------------------------------------ #

def _make_skill(
    name: str = "Python",
    name_slug: str = "python",
    proficiency: int = 3,
    source: str = "manual",
    category: str = None,
    skill_id: uuid.UUID = None,
    user_id: uuid.UUID = None,
) -> MagicMock:
    skill = MagicMock(spec=Skill)
    skill.id = skill_id or uuid.uuid4()
    skill.user_id = user_id or uuid.uuid4()
    skill.name = name
    skill.name_slug = name_slug
    skill.category = category
    skill.proficiency = proficiency
    skill.source = source
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    skill.created_at = now
    skill.updated_at = now
    return skill


def _make_service(repo_overrides: dict = None) -> tuple[SkillsService, MagicMock]:
    repo = MagicMock()
    repo.get_by_slug = AsyncMock(return_value=None)
    repo.get_by_id = AsyncMock(return_value=None)
    repo.find_all = AsyncMock(return_value=[])
    def _populate_mock(s):
        if not s.id: s.id = uuid.uuid4()
        if not s.user_id: s.user_id = uuid.uuid4()
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        if not s.created_at: s.created_at = now
        if not s.updated_at: s.updated_at = now
        return s
        
    repo.create = AsyncMock(side_effect=_populate_mock)
    repo.update = AsyncMock(side_effect=_populate_mock)
    repo.delete = AsyncMock()
    if repo_overrides:
        for k, v in repo_overrides.items():
            setattr(repo, k, v)
    service = SkillsService(skill_repo=repo)
    return service, repo


# ------------------------------------------------------------------ #
# create_skill
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_create_skill_happy_path():
    service, repo = _make_service()
    skill = _make_skill()
    repo.create.return_value = skill

    dto = SkillCreate(name="Python", proficiency=4)
    result = await service.create_skill(dto)

    repo.get_by_slug.assert_called_once_with("python")
    repo.create.assert_called_once()
    assert result.name == "Python"


@pytest.mark.asyncio
async def test_create_skill_duplicate_raises_409():
    existing = _make_skill(name="React", name_slug="react")
    service, repo = _make_service({"get_by_slug": AsyncMock(return_value=existing)})

    dto = SkillCreate(name="REACT")
    with pytest.raises(AppException) as exc_info:
        await service.create_skill(dto)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "SKILL_DUPLICATE"


@pytest.mark.asyncio
async def test_create_skill_case_insensitive_dedup():
    """'react', 'React', 'REACT' all produce the same slug and hit the duplicate guard."""
    existing = _make_skill(name="react", name_slug="react")
    service, repo = _make_service({"get_by_slug": AsyncMock(return_value=existing)})

    for variant in ["React", "REACT", "react"]:
        with pytest.raises(AppException) as exc_info:
            await service.create_skill(SkillCreate(name=variant))
        assert exc_info.value.status_code == 409


# ------------------------------------------------------------------ #
# upsert_skill
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_upsert_skill_creates_when_not_exists():
    service, repo = _make_service()
    skill = _make_skill(name="Docker", name_slug="docker")
    repo.create.return_value = skill

    result = await service.upsert_skill(name="Docker", source="cv_import")
    repo.create.assert_called_once()
    assert result.name == "Docker"


@pytest.mark.asyncio
async def test_upsert_skill_updates_existing():
    existing = _make_skill(name="Docker", name_slug="docker", proficiency=2)
    service, repo = _make_service({"get_by_slug": AsyncMock(return_value=existing)})
    repo.update.return_value = existing

    result = await service.upsert_skill(name="Docker", proficiency=4)
    repo.update.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_skill_no_update_when_unchanged():
    """If nothing changes, upsert should not call repo.update."""
    existing = _make_skill(name="Docker", name_slug="docker", proficiency=3, source="manual")
    service, repo = _make_service({"get_by_slug": AsyncMock(return_value=existing)})

    result = await service.upsert_skill(name="Docker", proficiency=3, source="manual")
    repo.update.assert_not_called()


# ------------------------------------------------------------------ #
# get_skill
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_get_skill_not_found_raises_404():
    service, repo = _make_service()
    with pytest.raises(NotFoundError):
        await service.get_skill(uuid.uuid4())


@pytest.mark.asyncio
async def test_get_skill_returns_response():
    skill = _make_skill()
    service, repo = _make_service({"get_by_id": AsyncMock(return_value=skill)})
    result = await service.get_skill(skill.id)
    assert result.id == skill.id


# ------------------------------------------------------------------ #
# update_skill
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_update_skill_not_found_raises_404():
    service, repo = _make_service()
    with pytest.raises(NotFoundError):
        await service.update_skill(uuid.uuid4(), SkillUpdate(name="New Name"))


@pytest.mark.asyncio
async def test_update_skill_name_conflict_raises_409():
    target = _make_skill(name="Python", name_slug="python")
    conflict = _make_skill(name="typescript", name_slug="typescript")

    async def mock_get_slug(slug):
        if slug == "typescript":
            return conflict
        return None

    service, repo = _make_service({
        "get_by_id": AsyncMock(return_value=target),
        "get_by_slug": AsyncMock(side_effect=mock_get_slug),
    })

    with pytest.raises(AppException) as exc_info:
        await service.update_skill(target.id, SkillUpdate(name="TypeScript"))
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_update_skill_happy_path():
    skill = _make_skill(name="Python", name_slug="python", proficiency=3)
    service, repo = _make_service({
        "get_by_id": AsyncMock(return_value=skill),
        "get_by_slug": AsyncMock(return_value=None),
        "update": AsyncMock(return_value=skill),
    })
    result = await service.update_skill(skill.id, SkillUpdate(proficiency=5))
    repo.update.assert_called_once()


# ------------------------------------------------------------------ #
# delete_skill
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_delete_skill_not_found_raises_404():
    service, repo = _make_service()
    with pytest.raises(NotFoundError):
        await service.delete_skill(uuid.uuid4())


@pytest.mark.asyncio
async def test_delete_skill_happy_path():
    skill = _make_skill()
    service, repo = _make_service({"get_by_id": AsyncMock(return_value=skill)})
    await service.delete_skill(skill.id)
    repo.delete.assert_called_once_with(skill)


# ------------------------------------------------------------------ #
# list_skills
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_list_skills_empty():
    service, repo = _make_service()
    result = await service.list_skills()
    assert result == []


@pytest.mark.asyncio
async def test_list_skills_returns_all():
    skills = [_make_skill(name=f"Skill{i}", name_slug=f"skill{i}") for i in range(3)]
    service, repo = _make_service({"find_all": AsyncMock(return_value=skills)})
    result = await service.list_skills()
    assert len(result) == 3
