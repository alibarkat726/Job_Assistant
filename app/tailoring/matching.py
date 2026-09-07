"""
Matching Engine — pure skill-slug scoring logic.

Compares a parsed JD's requirements against the user's canonical skill graph
using the same normalization strategy from Module 3 (normalize_skill_name).

Design: NO LLM dependency — this is deterministic slug-overlap scoring.
Semantic/embedding-based matching is a future upgrade (noted in README).

Independently unit-testable without any database or agent calls.
"""
from typing import List, Sequence
import uuid
from app.core_schema.models import Skill, Project, ProjectSkill
from app.skills.services import normalize_skill_name
from app.tailoring.schemas import (
    StructuredJDRequirement,
    SkillMatchResult,
    ProjectRelevanceResult,
    MatchingReport,
)


def score_skills(
    jd_requirements: List[StructuredJDRequirement],
    user_skills: Sequence[Skill],
) -> List[SkillMatchResult]:
    """
    Match each JD requirement against the user's canonical skill graph.

    Matching strategy (skill-slug overlap):
      - Build a map of {slug: skill} from the user's skills.
      - For each JD requirement, normalize its name to a slug and look it up.
      - matched:  exact slug match found in user's skill graph
      - partial:  no exact match, but user has a skill whose slug CONTAINS the JD slug
                  or vice-versa (e.g. user has "node.js", JD asks for "node")
      - missing:  no match at all

    NOTE: This is intentionally keyword-based. Semantic/embedding-based upgrades
    (e.g. "Backend" matching "FastAPI") can be layered on top later without
    changing this function's signature or callers.
    """
    user_skill_map = {skill.name_slug: skill for skill in user_skills}

    results: List[SkillMatchResult] = []
    for req in jd_requirements:
        jd_slug = normalize_skill_name(req.skill_name)
        match_status = "missing"
        matched_id = None
        matched_name = None
        proficiency = None

        if jd_slug in user_skill_map:
            skill = user_skill_map[jd_slug]
            match_status = "matched"
            matched_id = skill.id
            matched_name = skill.name
            proficiency = skill.proficiency
        else:
            # Partial match: slug contains/is contained by a user skill slug
            for slug, skill in user_skill_map.items():
                if jd_slug in slug or slug in jd_slug:
                    match_status = "partial"
                    matched_id = skill.id
                    matched_name = skill.name
                    proficiency = skill.proficiency
                    break

        results.append(SkillMatchResult(
            jd_skill_name=req.skill_name,
            jd_skill_slug=jd_slug,
            match_status=match_status,
            matched_skill_id=matched_id,
            matched_skill_name=matched_name,
            user_proficiency=proficiency,
            is_required=req.is_required,
        ))

    return results


def rank_projects(
    jd_requirements: List[StructuredJDRequirement],
    user_projects: Sequence[Project],
) -> List[ProjectRelevanceResult]:
    """
    Rank user projects by their relevance to the JD.

    Uses the project->skill many-to-many relationship (from Module 3's project_skills).
    Score = matched_skill_count / total_jd_required_skills.
    Projects with no skill attachments receive a score of 0.
    """
    jd_slugs = {normalize_skill_name(req.skill_name) for req in jd_requirements}
    total_jd_skills = len(jd_slugs)

    results: List[ProjectRelevanceResult] = []
    for project in user_projects:
        matched_names = []
        project_skill_slugs = set()
        if project.project_skills:
            for ps in project.project_skills:
                if ps.skill:
                    project_skill_slugs.add(ps.skill.name_slug)

        for jd_slug in jd_slugs:
            # Direct match or partial
            for p_slug in project_skill_slugs:
                if jd_slug == p_slug or jd_slug in p_slug or p_slug in jd_slug:
                    # Find original name for display
                    for ps in project.project_skills:
                        if ps.skill and ps.skill.name_slug == p_slug:
                            matched_names.append(ps.skill.name)
                    break

        matched_count = len(matched_names)
        score = matched_count / total_jd_skills if total_jd_skills > 0 else 0.0

        results.append(ProjectRelevanceResult(
            project_id=project.id,
            project_title=project.title,
            matched_skill_count=matched_count,
            total_jd_skills=total_jd_skills,
            relevance_score=round(score, 3),
            matched_skill_names=matched_names,
        ))

    # Sort by relevance score descending
    results.sort(key=lambda r: r.relevance_score, reverse=True)
    return results


def build_matching_report(
    jd_requirements: List[StructuredJDRequirement],
    user_skills: Sequence[Skill],
    user_projects: Sequence[Project],
) -> MatchingReport:
    """Build the full matching report combining skill and project scores."""
    skill_matches = score_skills(jd_requirements, user_skills)
    project_rankings = rank_projects(jd_requirements, user_projects)

    required_matches = [m for m in skill_matches if m.is_required]
    matched_required = sum(1 for m in required_matches if m.match_status in ("matched", "partial"))
    missing_required = sum(1 for m in required_matches if m.match_status == "missing")
    total_required = len(required_matches)
    overall_score = matched_required / total_required if total_required > 0 else 0.0

    return MatchingReport(
        skill_matches=skill_matches,
        project_rankings=project_rankings,
        overall_match_score=round(overall_score, 3),
        missing_required_count=missing_required,
        matched_required_count=matched_required,
    )
