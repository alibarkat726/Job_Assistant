"""
Unit tests for the Matching Engine (matching.py).
Pure function tests — no database, no LLM.
Verifies matched / partial / missing scoring and project relevance ranking.
"""
import uuid
import pytest
from unittest.mock import MagicMock
from app.tailoring.matching import score_skills, rank_projects, build_matching_report
from app.tailoring.schemas import StructuredJDRequirement


def make_skill(name: str, slug: str, proficiency: int = 3):
    s = MagicMock()
    s.id = uuid.uuid4()
    s.name = name
    s.name_slug = slug
    s.proficiency = proficiency
    return s


def make_project(title: str, skill_slugs: list[str]):
    p = MagicMock()
    p.id = uuid.uuid4()
    p.title = title
    ps_list = []
    for slug in skill_slugs:
        ps = MagicMock()
        ps.skill = make_skill(slug.title(), slug)
        ps_list.append(ps)
    p.project_skills = ps_list
    return p


def make_jd_req(skill_name: str, is_required: bool = True):
    return StructuredJDRequirement(skill_name=skill_name, is_required=is_required)


# ------------------------------------------------------------------ #
# score_skills tests
# ------------------------------------------------------------------ #

def test_matched_skill():
    user_skills = [make_skill("Python", "python", proficiency=5)]
    jd_reqs = [make_jd_req("Python")]
    results = score_skills(jd_reqs, user_skills)
    assert len(results) == 1
    assert results[0].match_status == "matched"
    assert results[0].user_proficiency == 5
    assert results[0].matched_skill_name == "Python"


def test_partial_match_slug_overlap():
    user_skills = [make_skill("Node.js", "node.js")]
    jd_reqs = [make_jd_req("Node")]  # Shorter form — should partial-match
    results = score_skills(jd_reqs, user_skills)
    assert results[0].match_status == "partial"


def test_missing_skill():
    user_skills = [make_skill("Python", "python")]
    jd_reqs = [make_jd_req("Kubernetes")]
    results = score_skills(jd_reqs, user_skills)
    assert results[0].match_status == "missing"
    assert results[0].user_proficiency is None


def test_case_insensitive_matching():
    user_skills = [make_skill("FastAPI", "fastapi")]
    jd_reqs = [make_jd_req("FASTAPI")]  # uppercase in JD
    results = score_skills(jd_reqs, user_skills)
    assert results[0].match_status == "matched"


def test_mixed_matched_and_missing():
    user_skills = [make_skill("Python", "python"), make_skill("Docker", "docker")]
    jd_reqs = [make_jd_req("Python"), make_jd_req("Kubernetes"), make_jd_req("Docker")]
    results = score_skills(jd_reqs, user_skills)

    statuses = {r.jd_skill_slug: r.match_status for r in results}
    assert statuses["python"] == "matched"
    assert statuses["docker"] == "matched"
    assert statuses["kubernetes"] == "missing"


# ------------------------------------------------------------------ #
# rank_projects tests
# ------------------------------------------------------------------ #

def test_project_ranked_by_relevance():
    jd_reqs = [make_jd_req("Python"), make_jd_req("FastAPI"), make_jd_req("Docker")]
    p1 = make_project("API Project", ["python", "fastapi", "docker"])  # 3/3
    p2 = make_project("Frontend Project", ["react", "typescript"])       # 0/3
    results = rank_projects(jd_reqs, [p2, p1])  # pass out of order
    assert results[0].project_title == "API Project"
    assert results[0].relevance_score == 1.0
    assert results[1].relevance_score == 0.0


def test_project_with_no_skills_scores_zero():
    jd_reqs = [make_jd_req("Python")]
    p = make_project("Empty Project", [])
    results = rank_projects(jd_reqs, [p])
    assert results[0].relevance_score == 0.0


# ------------------------------------------------------------------ #
# build_matching_report tests
# ------------------------------------------------------------------ #

def test_overall_score_only_counts_required():
    user_skills = [make_skill("Python", "python")]
    jd_reqs = [
        make_jd_req("Python", is_required=True),
        make_jd_req("GraphQL", is_required=False),  # Nice-to-have; missing but should NOT hurt score
    ]
    report = build_matching_report(jd_reqs, user_skills, [])
    assert report.matched_required_count == 1
    assert report.missing_required_count == 0
    assert report.overall_match_score == 1.0


def test_missing_required_reduces_score():
    user_skills = [make_skill("Python", "python")]
    jd_reqs = [
        make_jd_req("Python", is_required=True),
        make_jd_req("Kubernetes", is_required=True),  # Missing required
    ]
    report = build_matching_report(jd_reqs, user_skills, [])
    assert report.matched_required_count == 1
    assert report.missing_required_count == 1
    assert report.overall_match_score == 0.5
