"""
Unit tests for ProjectsService.

These tests use mock repositories to isolate service logic without hitting the database.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.projects.services import ProjectsService
from app.projects.schemas import ProjectCreate, ProjectUpdate, ProjectUrlSchema
from app.core_schema.models import Project, ProjectSkill, Skill
from app.shared.middleware.error_handler import NotFoundError, AppException


# ------------------------------------------------------------------ #
# Helper factories
# ------------------------------------------------------------------ #

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_skill(name: str = "Python", name_slug: str = "python") -> MagicMock:
    s = MagicMock(spec=Skill)
    s.id = uuid.uuid4()
    s.user_id = uuid.uuid4()
    s.name = name
    s.name_slug = name_slug
    s.category = None
    s.proficiency = 3
    s.source = "manual"
    s.created_at = _now()
    s.updated_at = _now()
    return s


def _make_project(title: str = "AI Agent", skills: list = None) -> MagicMock:
    p = MagicMock(spec=Project)
    p.id = uuid.uuid4()
    p.user_id = uuid.uuid4()
    p.title = title
    p.description = None
    p.urls = []
    p.start_date = None
    p.end_date = None
    p.is_ongoing = False
    p.project_skills = skills or []
    p.created_at = _now()
    p.updated_at = _now()
    return p


def _make_project_skill_link(project: MagicMock, skill: MagicMock) -> MagicMock:
    ps = MagicMock(spec=ProjectSkill)
    ps.project_id = project.id
    ps.skill_id = skill.id
    ps.skill = skill
    return ps


def _make_service(project_overrides=None, skill_overrides=None):
    project_repo = MagicMock()
    project_repo.create = AsyncMock(side_effect=lambda p: p)
    project_repo.update = AsyncMock(side_effect=lambda p: p)
    project_repo.delete = AsyncMock()
    project_repo.get_by_id = AsyncMock(return_value=None)
    project_repo.get_with_skills = AsyncMock(return_value=None)
    project_repo.find_all_with_skills = AsyncMock(return_value=[])
    project_repo.get_project_skill_link = AsyncMock(return_value=None)
    project_repo.add_skill = AsyncMock()
    project_repo.remove_skill = AsyncMock()
    project_repo.get_project_skills = AsyncMock(return_value=[])
    if project_overrides:
        for k, v in project_overrides.items():
            setattr(project_repo, k, v)

    skill_repo = MagicMock()
    skill_repo.get_by_id = AsyncMock(return_value=None)
    if skill_overrides:
        for k, v in skill_overrides.items():
            setattr(skill_repo, k, v)

    service = ProjectsService(project_repo=project_repo, skill_repo=skill_repo)
    return service, project_repo, skill_repo


# ------------------------------------------------------------------ #
# create_project
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_create_project_happy_path():
    project = _make_project()
    service, project_repo, _ = _make_service(
        {"create": AsyncMock(return_value=project)}
    )
    dto = ProjectCreate(title="My AI Agent")
    result = await service.create_project(dto)
    project_repo.create.assert_called_once()
    assert result.title == "AI Agent"


@pytest.mark.asyncio
async def test_create_project_with_urls():
    project = _make_project()
    project.urls = [{"label": "GitHub", "url": "https://github.com/test"}]
    service, project_repo, _ = _make_service(
        {"create": AsyncMock(return_value=project)}
    )
    dto = ProjectCreate(
        title="My Project",
        urls=[ProjectUrlSchema(label="GitHub", url="https://github.com/test")],
    )
    result = await service.create_project(dto)
    assert len(result.urls) == 1


@pytest.mark.asyncio
async def test_create_project_invalid_url_raises_validation_error():
    """Pydantic should reject URLs that don't start with http:// or https://."""
    with pytest.raises(Exception):
        ProjectCreate(
            title="My Project",
            urls=[ProjectUrlSchema(url="ftp://invalid.com")],
        )


# ------------------------------------------------------------------ #
# get_project
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_get_project_not_found_raises_404():
    service, _, _ = _make_service()
    with pytest.raises(NotFoundError):
        await service.get_project(uuid.uuid4())


@pytest.mark.asyncio
async def test_get_project_returns_response():
    project = _make_project()
    service, project_repo, _ = _make_service(
        {"get_with_skills": AsyncMock(return_value=project)}
    )
    result = await service.get_project(project.id)
    assert result.id == project.id


# ------------------------------------------------------------------ #
# update_project
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_update_project_not_found_raises_404():
    service, _, _ = _make_service()
    with pytest.raises(NotFoundError):
        await service.update_project(uuid.uuid4(), ProjectUpdate(title="New"))


@pytest.mark.asyncio
async def test_update_project_title():
    project = _make_project(title="Old Title")
    updated = _make_project(title="New Title")
    service, project_repo, _ = _make_service({
        "get_with_skills": AsyncMock(side_effect=[project, updated]),
        "update": AsyncMock(return_value=project),
    })
    result = await service.update_project(project.id, ProjectUpdate(title="New Title"))
    project_repo.update.assert_called_once()


# ------------------------------------------------------------------ #
# delete_project
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_delete_project_not_found_raises_404():
    service, _, _ = _make_service()
    with pytest.raises(NotFoundError):
        await service.delete_project(uuid.uuid4())


@pytest.mark.asyncio
async def test_delete_project_happy_path():
    project = _make_project()
    service, project_repo, _ = _make_service(
        {"get_by_id": AsyncMock(return_value=project)}
    )
    await service.delete_project(project.id)
    project_repo.delete.assert_called_once_with(project)


# ------------------------------------------------------------------ #
# attach_skill
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_attach_skill_project_not_found_raises_404():
    service, _, _ = _make_service()
    with pytest.raises(NotFoundError):
        await service.attach_skill(uuid.uuid4(), uuid.uuid4())


@pytest.mark.asyncio
async def test_attach_skill_skill_not_found_raises_404():
    """Attaching a skill that doesn't belong to this tenant raises 404."""
    project = _make_project()
    service, _, _ = _make_service(
        {"get_with_skills": AsyncMock(return_value=project)}
    )
    with pytest.raises(NotFoundError):
        await service.attach_skill(project.id, uuid.uuid4())


@pytest.mark.asyncio
async def test_attach_skill_duplicate_raises_409():
    """Attaching a skill that's already attached raises 409."""
    project = _make_project()
    skill = _make_skill()
    existing_link = MagicMock()

    service, project_repo, skill_repo = _make_service(
        {"get_with_skills": AsyncMock(return_value=project),
         "get_project_skill_link": AsyncMock(return_value=existing_link)},
        {"get_by_id": AsyncMock(return_value=skill)},
    )

    with pytest.raises(AppException) as exc_info:
        await service.attach_skill(project.id, skill.id)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "SKILL_ALREADY_ATTACHED"


@pytest.mark.asyncio
async def test_attach_skill_happy_path():
    project = _make_project()
    skill = _make_skill()
    refreshed = _make_project()

    service, project_repo, skill_repo = _make_service(
        {"get_with_skills": AsyncMock(side_effect=[project, refreshed]),
         "get_project_skill_link": AsyncMock(return_value=None),
         "add_skill": AsyncMock()},
        {"get_by_id": AsyncMock(return_value=skill)},
    )

    result = await service.attach_skill(project.id, skill.id)
    project_repo.add_skill.assert_called_once_with(project.id, skill.id)


# ------------------------------------------------------------------ #
# detach_skill
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_detach_skill_project_not_found_raises_404():
    service, _, _ = _make_service()
    with pytest.raises(NotFoundError):
        await service.detach_skill(uuid.uuid4(), uuid.uuid4())


@pytest.mark.asyncio
async def test_detach_skill_not_attached_raises_404():
    """Detaching a skill that is not attached raises 404."""
    project = _make_project()
    service, project_repo, _ = _make_service({
        "get_with_skills": AsyncMock(return_value=project),
        "get_project_skill_link": AsyncMock(return_value=None),
    })
    with pytest.raises(NotFoundError):
        await service.detach_skill(project.id, uuid.uuid4())


@pytest.mark.asyncio
async def test_detach_skill_happy_path():
    project = _make_project()
    existing_link = MagicMock()
    refreshed = _make_project()

    service, project_repo, _ = _make_service({
        "get_with_skills": AsyncMock(side_effect=[project, refreshed]),
        "get_project_skill_link": AsyncMock(return_value=existing_link),
        "remove_skill": AsyncMock(),
    })

    result = await service.detach_skill(project.id, uuid.uuid4())
    project_repo.remove_skill.assert_called_once()
