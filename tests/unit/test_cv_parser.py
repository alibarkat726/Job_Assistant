import pytest
from app.cv.parser import IntakeAgentService, HeuristicCVParser
from app.cv.schemas import StructuredCVSchema


@pytest.mark.asyncio
async def test_heuristic_parser_extraction():
    parser = HeuristicCVParser()
    sample_text = """
    Alice Smith
    alice.smith@example.com | +1-555-0199
    San Francisco, CA

    Professional Summary
    Senior Software Engineer with 6 years of experience building Python and FastAPI services.

    Work Experience
    Senior Developer - Tech Corp
    Developed high-throughput async APIs using Python, FastAPI, and PostgreSQL.

    Education
    Bachelor of Science in Computer Science - University of California

    Skills
    Python, FastAPI, PostgreSQL, Docker, AWS
    """

    result: StructuredCVSchema = await parser.parse_cv_text(sample_text)

    assert result.contact_info.email == "alice.smith@example.com"
    assert result.contact_info.phone == "+1-555-0199"
    assert "Python" in result.skills
    assert "FastAPI" in result.skills
    assert len(result.work_history) >= 1
    assert len(result.education) >= 1


@pytest.mark.asyncio
async def test_intake_agent_service_fallback_chain():
    intake_agent = IntakeAgentService()

    # Test empty string fallback
    empty_result = await intake_agent.parse_raw_cv("")
    assert empty_result.parse_confidence == "low"
    assert "Uploaded document did not contain parseable text." in empty_result.parsing_notes[0]

    # Test valid text parsing
    text = "Bob Jones\nbob@example.com\nPython Developer"
    valid_result = await intake_agent.parse_raw_cv(text)
    assert valid_result.contact_info.email == "bob@example.com"
