"""
Integration tests for Module 6 (Interview Prep).
Tests generating a prep set for a job application, fetching it, updating questions,
and ensuring tenant isolation.
"""
import pytest
from httpx import AsyncClient

SAMPLE_JD = """
Backend Developer

Requirements:
- Python
- PostgreSQL
"""


@pytest.mark.asyncio
async def test_full_interview_prep_flow(async_client: AsyncClient, test_user_a: dict):
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}

    # 1. Create a Job Application
    create_app_resp = await async_client.post(
        "/api/v1/applications",
        headers=headers,
        json={
            "job_title": "Backend Dev",
            "jd_raw_text": SAMPLE_JD,
        }
    )
    assert create_app_resp.status_code == 201
    app_id = create_app_resp.json()["id"]

    # 2. Generate Interview Prep
    gen_resp = await async_client.post(f"/api/v1/applications/{app_id}/interview-prep", headers=headers)
    assert gen_resp.status_code == 201
    prep_set = gen_resp.json()
    assert prep_set["status"] == "generated"
    assert len(prep_set["questions"]) > 0

    # 3. Retrieve Interview Prep
    get_resp = await async_client.get(f"/api/v1/applications/{app_id}/interview-prep", headers=headers)
    assert get_resp.status_code == 200
    retrieved_set = get_resp.json()
    assert retrieved_set["id"] == prep_set["id"]

    # 4. Update a Question
    q_id = retrieved_set["questions"][0]["id"]
    update_resp = await async_client.put(
        f"/api/v1/applications/{app_id}/interview-prep/questions/{q_id}",
        headers=headers,
        json={"user_notes": "My practice answer", "is_practiced": True}
    )
    assert update_resp.status_code == 200
    updated_q = update_resp.json()
    assert updated_q["user_notes"] == "My practice answer"
    assert updated_q["is_practiced"] is True

    # 5. Regenerate Interview Prep
    regen_resp = await async_client.post(f"/api/v1/applications/{app_id}/interview-prep", headers=headers)
    assert regen_resp.status_code == 201
    new_prep_set = regen_resp.json()
    # The IDs should be different because the old set was deleted
    assert new_prep_set["id"] != prep_set["id"]


@pytest.mark.asyncio
async def test_tenant_isolation_interview_prep(async_client: AsyncClient, test_user_a: dict, test_user_b: dict):
    """User B cannot access User A's interview prep set."""
    headers_a = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}
    headers_b = {"Authorization": f"Bearer {test_user_b['tokens'].access_token}"}

    # User A creates an application and prep set
    create_a = await async_client.post(
        "/api/v1/applications",
        headers=headers_a,
        json={"job_title": "Role A", "jd_raw_text": SAMPLE_JD}
    )
    app_id_a = create_a.json()["id"]

    gen_a = await async_client.post(f"/api/v1/applications/{app_id_a}/interview-prep", headers=headers_a)
    prep_id_a = gen_a.json()["id"]
    q_id_a = gen_a.json()["questions"][0]["id"]

    # User B cannot generate for A's application
    gen_b = await async_client.post(f"/api/v1/applications/{app_id_a}/interview-prep", headers=headers_b)
    assert gen_b.status_code == 404

    # User B cannot get A's prep set
    get_b = await async_client.get(f"/api/v1/applications/{app_id_a}/interview-prep", headers=headers_b)
    assert get_b.status_code == 404

    # User B cannot update A's question
    update_b = await async_client.put(
        f"/api/v1/applications/{app_id_a}/interview-prep/questions/{q_id_a}",
        headers=headers_b,
        json={"user_notes": "hacked"}
    )
    assert update_b.status_code == 404
