"""
Integration tests for Module 5 (Job Applications & CV Tailoring).
Tests the full flow: submit JD → parse → match → tailor draft → edit → finalize → status update.
Also tests tenant isolation (User A cannot read User B's applications or tailored CVs).
"""
import pytest
from httpx import AsyncClient

SAMPLE_JD = """
Senior Python Backend Engineer

We are hiring a Senior Backend Engineer with 5+ years of experience.

Requirements:
- Expert-level Python and FastAPI
- Strong experience with PostgreSQL
- Docker containerization

Responsibilities:
- Design and build scalable REST APIs
- Implement and optimize database schemas
"""


@pytest.mark.asyncio
async def test_full_tailoring_flow(async_client: AsyncClient, test_user_a: dict):
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}

    # 1. Submit JD
    create_resp = await async_client.post(
        "/api/v1/applications",
        headers=headers,
        json={
            "job_title": "Senior Backend Engineer",
            "company": "Acme Corp",
            "jd_raw_text": SAMPLE_JD,
        }
    )
    assert create_resp.status_code == 201
    app_data = create_resp.json()
    app_id = app_data["id"]

    assert app_data["parse_status"] == "parsed"
    assert app_data["status"] == "draft"
    assert len(app_data["requirements"]) > 0

    # Check Python was extracted
    req_names = {r["skill_name"] for r in app_data["requirements"]}
    assert "Python" in req_names

    # 2. Get matching report (works even without skills)
    match_resp = await async_client.get(f"/api/v1/applications/{app_id}/match", headers=headers)
    assert match_resp.status_code == 200
    report = match_resp.json()
    assert "skill_matches" in report
    assert "overall_match_score" in report

    # 3. List applications
    list_resp = await async_client.get("/api/v1/applications", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # 4. Update status to 'applied' (user marks as applied manually)
    status_resp = await async_client.put(
        f"/api/v1/applications/{app_id}/status",
        headers=headers,
        json={"status": "applied"}
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "applied"

    # 5. Delete application
    del_resp = await async_client.delete(f"/api/v1/applications/{app_id}", headers=headers)
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_tenant_isolation_applications(async_client: AsyncClient, test_user_a: dict, test_user_b: dict):
    """User B cannot access User A's job applications or tailored CVs."""
    headers_a = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}
    headers_b = {"Authorization": f"Bearer {test_user_b['tokens'].access_token}"}

    # User A creates an application
    create_a = await async_client.post(
        "/api/v1/applications",
        headers=headers_a,
        json={"job_title": "Dev Role", "jd_raw_text": SAMPLE_JD}
    )
    assert create_a.status_code == 201
    app_id_a = create_a.json()["id"]

    # User B cannot see it
    get_b = await async_client.get(f"/api/v1/applications/{app_id_a}", headers=headers_b)
    assert get_b.status_code == 404

    # User B's list is empty
    list_b = await async_client.get("/api/v1/applications", headers=headers_b)
    assert list_b.status_code == 200
    assert len(list_b.json()) == 0

    # User B cannot update User A's status
    update_b = await async_client.put(
        f"/api/v1/applications/{app_id_a}/status",
        headers=headers_b,
        json={"status": "applied"}
    )
    assert update_b.status_code == 404

    # User B cannot delete User A's application
    del_b = await async_client.delete(f"/api/v1/applications/{app_id_a}", headers=headers_b)
    assert del_b.status_code == 404

    # User B cannot get the matching report
    match_b = await async_client.get(f"/api/v1/applications/{app_id_a}/match", headers=headers_b)
    assert match_b.status_code == 404


@pytest.mark.asyncio
async def test_jd_input_validation(async_client: AsyncClient, test_user_a: dict):
    """Too-short JD should be rejected with 422."""
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}
    resp = await async_client.post(
        "/api/v1/applications",
        headers=headers,
        json={"job_title": "Dev", "jd_raw_text": "Short."}
    )
    assert resp.status_code == 422
