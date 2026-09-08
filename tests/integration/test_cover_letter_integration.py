"""
Integration tests for Cover Letter module (Module 8).
Full flow: generate → edit → finalize → export, plus tenant isolation.
"""
import pytest
from httpx import AsyncClient

SAMPLE_CV = (
    b"Jane Doe\njane@example.com | +1-555-1234\nNew York, NY\n\n"
    b"Experience\nBackend Engineer - Tech Corp\nBuilt scalable APIs in Python.\n\n"
    b"Education\nBS Computer Science - MIT\n\n"
    b"Skills\nPython, PostgreSQL, FastAPI"
)

SAMPLE_JD = """
Backend Engineer at Acme

Requirements:
- Python
- PostgreSQL
"""


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

async def _setup_user(client: AsyncClient, headers: dict) -> str:
    """Upload + finalize a CV, add a skill, add a project, and submit a JD.
    Returns the job_application id."""
    await client.post(
        "/api/v1/cvs/upload",
        headers=headers,
        files={"file": ("cv.txt", SAMPLE_CV, "text/plain")}
    )
    await client.post("/api/v1/cvs/finalize", headers=headers)
    await client.post("/api/v1/skills", headers=headers, json={"name": "Python", "proficiency": 4})
    await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"title": "API Service", "description": "Built an API in Python.", "proficiency_level": 4, "is_public": True, "urls": {}}
    )
    app_resp = await client.post(
        "/api/v1/applications",
        headers=headers,
        json={"job_title": "Backend Engineer", "company": "Acme", "jd_raw_text": SAMPLE_JD}
    )
    return app_resp.json()["id"]


# ------------------------------------------------------------------ #
# Full Flow Test
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_cover_letter_full_flow(async_client: AsyncClient, test_user_a: dict):
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}
    app_id = await _setup_user(async_client, headers)

    # 1. Generate Cover Letter (formal, short)
    gen_resp = await async_client.post(
        f"/api/v1/applications/{app_id}/cover-letter",
        headers=headers,
        json={"tone": "formal", "length": "short"}
    )
    assert gen_resp.status_code == 201, gen_resp.text
    cl_data = gen_resp.json()
    assert cl_data["status"] == "draft"
    assert cl_data["tone"] == "formal"
    assert cl_data["length"] == "short"
    assert "Backend Engineer" in cl_data["content"]
    assert "Python" in cl_data["content"]

    # 2. Get Cover Letter
    get_resp = await async_client.get(f"/api/v1/applications/{app_id}/cover-letter", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == cl_data["id"]

    # 3. Regenerate with different tone (should overwrite draft)
    regen_resp = await async_client.post(
        f"/api/v1/applications/{app_id}/cover-letter",
        headers=headers,
        json={"tone": "conversational", "length": "standard"}
    )
    assert regen_resp.status_code == 201
    regen_data = regen_resp.json()
    assert regen_data["tone"] == "conversational"
    assert regen_data["length"] == "standard"
    # Old draft is replaced — same app_id
    assert regen_data["job_application_id"] == app_id

    # 4. Edit Cover Letter
    edit_resp = await async_client.put(
        f"/api/v1/applications/{app_id}/cover-letter",
        headers=headers,
        json={"content": "Manually edited cover letter content."}
    )
    assert edit_resp.status_code == 200
    assert edit_resp.json()["content"] == "Manually edited cover letter content."

    # 5. Finalize
    fin_resp = await async_client.post(
        f"/api/v1/applications/{app_id}/cover-letter/finalize",
        headers=headers
    )
    assert fin_resp.status_code == 200
    assert fin_resp.json()["status"] == "finalized"

    # 6. Edit after finalize must fail
    fail_edit = await async_client.put(
        f"/api/v1/applications/{app_id}/cover-letter",
        headers=headers,
        json={"content": "Should not work"}
    )
    assert fail_edit.status_code == 400

    # 7. Export as plain text
    exp_resp = await async_client.get(
        f"/api/v1/applications/{app_id}/cover-letter/export",
        headers=headers
    )
    assert exp_resp.status_code == 200
    assert "text/plain" in exp_resp.headers["content-type"]
    assert exp_resp.text == "Manually edited cover letter content."


# ------------------------------------------------------------------ #
# Validation Tests
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_invalid_tone_rejected(async_client: AsyncClient, test_user_a: dict):
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}
    app_id = await _setup_user(async_client, headers)

    resp = await async_client.post(
        f"/api/v1/applications/{app_id}/cover-letter",
        headers=headers,
        json={"tone": "aggressive", "length": "short"}   # invalid tone
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_length_rejected(async_client: AsyncClient, test_user_a: dict):
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}
    app_id = await _setup_user(async_client, headers)

    resp = await async_client.post(
        f"/api/v1/applications/{app_id}/cover-letter",
        headers=headers,
        json={"tone": "formal", "length": "verbose"}   # invalid length
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_cover_letter_not_found(async_client: AsyncClient, test_user_a: dict):
    """Fetching a cover letter that hasn't been generated yet returns 404."""
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}
    app_id = await _setup_user(async_client, headers)

    resp = await async_client.get(f"/api/v1/applications/{app_id}/cover-letter", headers=headers)
    assert resp.status_code == 404


# ------------------------------------------------------------------ #
# Tenant Isolation Test
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_tenant_isolation_cover_letters(
    async_client: AsyncClient, test_user_a: dict, test_user_b: dict
):
    headers_a = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}
    headers_b = {"Authorization": f"Bearer {test_user_b['tokens'].access_token}"}

    # User A creates an application and generates a cover letter
    app_id = await _setup_user(async_client, headers_a)
    gen = await async_client.post(
        f"/api/v1/applications/{app_id}/cover-letter",
        headers=headers_a,
        json={"tone": "conversational", "length": "standard"}
    )
    assert gen.status_code == 201

    # User B tries to fetch User A's cover letter — must get 404
    fetch_b = await async_client.get(
        f"/api/v1/applications/{app_id}/cover-letter",
        headers=headers_b
    )
    assert fetch_b.status_code == 404

    # User B tries to export — must get 404
    export_b = await async_client.get(
        f"/api/v1/applications/{app_id}/cover-letter/export",
        headers=headers_b
    )
    assert export_b.status_code == 404

    # User B tries to finalize — must get 404
    fin_b = await async_client.post(
        f"/api/v1/applications/{app_id}/cover-letter/finalize",
        headers=headers_b
    )
    assert fin_b.status_code == 404
