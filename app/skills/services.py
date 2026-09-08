import logging
import re
from typing import List, Optional
import uuid
from app.shared.middleware.error_handler import NotFoundError, AppException
from app.core_schema.models import Skill
from app.skills.repository import SkillRepository
from app.skills.schemas import SkillCreate, SkillUpdate, SkillResponse

logger = logging.getLogger(__name__)


def normalize_skill_name(name: str) -> str:
    """
    Produce a deterministic, case-insensitive slug from a raw skill name.

    Strategy:
      1. Strip leading/trailing whitespace.
      2. Collapse any internal whitespace sequences to a single space.
      3. Convert to lowercase.

    Examples:
      "React.js"    → "react.js"
      "  C++  "     → "c++"
      "TypeScript"  → "typescript"
      "Node JS"     → "node js"

    Module 4 (Learning Triage) and Module 6 (Matching) always match on name_slug,
    never on the raw display name.
    """
    slug = name.strip()
    slug = re.sub(r"\s+", " ", slug)
    return slug.lower()


class SkillsService:
    """
    Service layer for canonical profile skill CRUD.

    Exposes `upsert_skill` as the programmatic interface for Module 4 (Learning Triage)
    to create/update skill records without going through HTTP routes.
    All write operations normalize the skill name to a slug for deduplication.
    """

    def __init__(self, skill_repo: SkillRepository):
        self.skill_repo = skill_repo

    async def create_skill(self, dto: SkillCreate) -> SkillResponse:
        """
        Create a new profile skill.
        Raises 409 Conflict if a skill with the same normalized name already exists.
        """
        name_slug = normalize_skill_name(dto.name)
        existing = await self.skill_repo.get_by_slug(name_slug)
        if existing:
            raise AppException(
                message=f"Skill '{dto.name}' (slug: '{name_slug}') already exists in your profile.",
                code="SKILL_DUPLICATE",
                status_code=409,
            )

        skill = Skill(
            name=dto.name.strip(),
            name_slug=name_slug,
            category=dto.category,
            proficiency=dto.proficiency,
            source=dto.source,
        )
        created = await self.skill_repo.create(skill)
        return self._map_to_response(created)

    async def upsert_skill(
        self,
        name: str,
        source: str = "manual",
        category: Optional[str] = None,
        proficiency: int = 3,
    ) -> SkillResponse:
        """
        Insert or update a skill based on normalized name_slug.

        This is the programmatic interface for Module 4 (Learning Triage) and
        CV import promotions — bypasses HTTP validation, operates directly on the
        service layer.

        If a skill with the same slug already exists:
          - Updates source, category, and proficiency if provided values differ.
        If not:
          - Creates a new skill record.
        """
        name_slug = normalize_skill_name(name)
        existing = await self.skill_repo.get_by_slug(name_slug)
        if existing:
            # Update if any values differ — always prefer more recent source
            changed = False
            if category is not None and existing.category != category:
                existing.category = category
                changed = True
            if existing.proficiency != proficiency:
                existing.proficiency = proficiency
                changed = True
            if existing.source != source:
                existing.source = source
                changed = True
            if changed:
                updated = await self.skill_repo.update(existing)
                return self._map_to_response(updated)
            return self._map_to_response(existing)

        skill = Skill(
            name=name.strip(),
            name_slug=name_slug,
            category=category,
            proficiency=proficiency,
            source=source,
        )
        created = await self.skill_repo.create(skill)
        return self._map_to_response(created)

    async def get_skill(self, skill_id: uuid.UUID) -> SkillResponse:
        """Fetch a single profile skill by ID. Raises 404 if not found."""
        skill = await self.skill_repo.get_by_id(skill_id)
        if not skill:
            raise NotFoundError(f"Skill with ID '{skill_id}' not found.")
        return self._map_to_response(skill)

    async def list_skills(self) -> List[SkillResponse]:
        """List all profile skills for the current tenant."""
        skills = await self.skill_repo.find_all()
        return [self._map_to_response(s) for s in skills]

    async def update_skill(self, skill_id: uuid.UUID, dto: SkillUpdate) -> SkillResponse:
        """
        Update a skill. If name changes, re-normalizes slug and checks for conflicts.
        Raises 404 if not found, 409 if the new name clashes with an existing skill.
        """
        skill = await self.skill_repo.get_by_id(skill_id)
        if not skill:
            raise NotFoundError(f"Skill with ID '{skill_id}' not found.")

        if dto.name is not None:
            new_slug = normalize_skill_name(dto.name)
            if new_slug != skill.name_slug:
                conflict = await self.skill_repo.get_by_slug(new_slug)
                if conflict and conflict.id != skill_id:
                    raise AppException(
                        message=f"Skill name '{dto.name}' conflicts with an existing skill.",
                        code="SKILL_DUPLICATE",
                        status_code=409,
                    )
            skill.name = dto.name.strip()
            skill.name_slug = new_slug

        if dto.category is not None:
            skill.category = dto.category or None
        if dto.proficiency is not None:
            skill.proficiency = dto.proficiency
        if dto.source is not None:
            skill.source = dto.source

        updated = await self.skill_repo.update(skill)
        return self._map_to_response(updated)

    async def delete_skill(self, skill_id: uuid.UUID) -> None:
        """Delete a profile skill. Raises 404 if not found."""
        skill = await self.skill_repo.get_by_id(skill_id)
        if not skill:
            raise NotFoundError(f"Skill with ID '{skill_id}' not found.")
        await self.skill_repo.delete(skill)

    def _map_to_response(self, skill: Skill) -> SkillResponse:
        return SkillResponse(
            id=skill.id,
            user_id=skill.user_id,
            name=skill.name,
            name_slug=skill.name_slug,
            category=skill.category,
            proficiency=skill.proficiency,
            source=skill.source,
            created_at=skill.created_at,
            updated_at=skill.updated_at,
        )
