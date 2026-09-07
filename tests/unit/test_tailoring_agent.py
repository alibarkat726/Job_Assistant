"""
Unit tests for HeuristicTailoringAgent.

Critical invariant: all underlying facts (company names, roles, dates, URLs)
must be preserved verbatim — only ORDER of work history entries may change.
"""
import uuid
import pytest
from unittest.mock import MagicMock
from app.tailoring.tailoring_agent import HeuristicTailoringAgent
from app.tailoring.schemas import MatchingReport, SkillMatchResult, ProjectRelevanceResult


def make_cv(work_entries: list[dict]):
    cv = MagicMock()
    cv.summary = "Experienced backend engineer."
    cv.id = uuid.uuid4()
    wh_list = []
    for e in work_entries:
        wh = MagicMock()
        wh.company = e["company"]
        wh.role = e["role"]
        wh.description = e.get("description", "")
        wh.location = e.get("location", None)
        wh.start_date = e.get("start_date", "2020")
        wh.end_date = e.get("end_date", "2022")
        wh.is_current = e.get("is_current", False)
        wh_list.append(wh)
    cv.work_histories = wh_list
    return cv


def make_matching_report(matched_slugs: list[str]) -> MatchingReport:
    skill_matches = [
        SkillMatchResult(
            jd_skill_name=s.title(),
            jd_skill_slug=s,
            match_status="matched",
            is_required=True,
        )
        for s in matched_slugs
    ]
    return MatchingReport(
        skill_matches=skill_matches,
        project_rankings=[],
        overall_match_score=1.0,
        missing_required_count=0,
        matched_required_count=len(matched_slugs),
    )


@pytest.fixture
def agent():
    return HeuristicTailoringAgent()


@pytest.mark.asyncio
async def test_verbatim_facts_preserved(agent):
    """Company names, roles, dates must be identical after tailoring."""
    cv = make_cv([
        {"company": "Acme Corp", "role": "Backend Dev", "description": "built python services", "start_date": "2020-01"},
        {"company": "Beta Inc", "role": "SRE", "description": "maintained kubernetes clusters", "start_date": "2022-01"},
    ])
    report = make_matching_report(["python"])
    draft = await agent.tailor(cv=cv, matching_report=report, top_projects=[])

    companies = {e["company"] for e in draft.tailored_work_history}
    assert "Acme Corp" in companies
    assert "Beta Inc" in companies

    for entry in draft.tailored_work_history:
        assert entry["start_date"] in ("2020-01", "2022-01")


@pytest.mark.asyncio
async def test_relevant_entry_surfaces_first(agent):
    """Entry mentioning matched JD skills should move to position 0."""
    cv = make_cv([
        {"company": "Unrelated Co", "role": "Manager", "description": "managed teams"},
        {"company": "Tech Corp", "role": "Engineer", "description": "built fastapi python rest api services"},
    ])
    report = make_matching_report(["python", "fastapi"])
    draft = await agent.tailor(cv=cv, matching_report=report, top_projects=[])

    assert draft.tailored_work_history[0]["company"] == "Tech Corp"


@pytest.mark.asyncio
async def test_no_new_fields_added(agent):
    """The tailored output should not add any fields not in the canonical CV."""
    cv = make_cv([
        {"company": "Firm A", "role": "Dev", "description": "worked on python", "start_date": "2021"},
    ])
    report = make_matching_report(["python"])
    draft = await agent.tailor(cv=cv, matching_report=report, top_projects=[])

    allowed_keys = {"company", "role", "location", "start_date", "end_date", "is_current", "description"}
    for entry in draft.tailored_work_history:
        for key in entry.keys():
            assert key in allowed_keys, f"Unexpected key '{key}' added to tailored work history"


@pytest.mark.asyncio
async def test_top_3_projects_selected(agent):
    """At most 3 projects should be selected."""
    cv = make_cv([{"company": "Corp", "role": "Dev", "description": "python"}])
    report = make_matching_report(["python"])
    projects = [MagicMock(id=uuid.uuid4(), title=f"Project {i}") for i in range(6)]
    draft = await agent.tailor(cv=cv, matching_report=report, top_projects=projects)

    assert len(draft.selected_project_ids) <= 3


@pytest.mark.asyncio
async def test_diff_summary_produced(agent):
    """A diff_summary should always be returned."""
    cv = make_cv([{"company": "A", "role": "Dev", "description": ""}])
    report = make_matching_report([])
    draft = await agent.tailor(cv=cv, matching_report=report, top_projects=[])

    assert isinstance(draft.diff_summary, str)
    assert len(draft.diff_summary) > 0
