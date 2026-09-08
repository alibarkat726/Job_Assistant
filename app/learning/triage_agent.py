from abc import ABC, abstractmethod
from typing import List, Optional
import re
from app.core_schema.models import Skill
from app.learning.schemas import TriageProposalOutput, TriageProposedSkill
from app.skills.services import normalize_skill_name


class ITriageAgent(ABC):
    """
    Interface for the Learning Triage Agent.
    Evaluates learning entries and produces structured proposals.
    """
    @abstractmethod
    async def classify_entry(self, entry_text: str, existing_skills: List[Skill]) -> TriageProposalOutput:
        pass


class HeuristicTriageAgent(ITriageAgent):
    """
    Deterministic rule-based triage agent for testing and fallback.
    Looks for keywords to determine skill-worthiness.
    """
    async def classify_entry(self, entry_text: str, existing_skills: List[Skill]) -> TriageProposalOutput:
        lower_text = entry_text.lower()
        
        # Simple heuristic for "not skill-worthy"
        if "read a blog" in lower_text or "watched a video" in lower_text:
            return TriageProposalOutput(
                is_skill_worthy=False,
                reasoning="Passive learning activities (reading/watching) without implementation are generally not considered skill-worthy on their own."
            )
            
        proposed_skills = []
        is_worthy = False
        reasoning = "No clear skill implementation detected."
        
        # Simple heuristic for "skill-worthy"
        if "built" in lower_text or "implemented" in lower_text or "learned" in lower_text:
            is_worthy = True
            reasoning = "Active implementation or learning detected."
            
            # Simple keyword extraction (simulating LLM extraction)
            tech_keywords = ["python", "fastapi", "react", "postgresql", "docker", "kubernetes", "typescript"]
            extracted = []
            for kw in tech_keywords:
                if kw in lower_text:
                    extracted.append(kw)
            
            # Fallback if no specific tech found but it's worthy
            if not extracted:
                extracted.append("General Engineering")
                
            for ext in extracted:
                ext_slug = normalize_skill_name(ext)
                # Match against existing skills
                matched_id = None
                action = "create_new"
                for skill in existing_skills:
                    if skill.name_slug == ext_slug:
                        matched_id = skill.id
                        action = "reinforce_existing"
                        break
                        
                proposed_skills.append(
                    TriageProposedSkill(
                        skill_name=ext.title() if ext != "fastapi" else "FastAPI",
                        action=action,
                        matched_skill_id=matched_id,
                        confidence="high" # Heuristic is highly confident in its deterministic matches
                    )
                )

        return TriageProposalOutput(
            is_skill_worthy=is_worthy,
            reasoning=reasoning,
            proposed_skills=proposed_skills
        )


class LLMTriageAgent(ITriageAgent):
    """
    Stub for LLM-powered Triage Agent.
    Validates output against Pydantic schema TriageProposalOutput.
    """
    async def classify_entry(self, entry_text: str, existing_skills: List[Skill]) -> TriageProposalOutput:
        # If an LLM client library is integrated in the future, invoke it here and parse response JSON
        # Validate response using TriageProposalOutput.model_validate_json(...)
        raise NotImplementedError("LLM parser client is currently unconfigured.")
