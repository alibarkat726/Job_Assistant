"""
Integration tests for Module 7 (Dashboard & Analytics).
Verifies database aggregation and tenant isolation.
"""
import pytest
from httpx import AsyncClient


SAMPLE_JD_1 = """
Backend Developer
Requirements:
- Python
- PostgreSQL
- Kubernetes
"""

SAMPLE_JD_2 = """
Senior Python Engineer
Requirements:
- Python
- Kubernetes
- Redis
"""

@pytest.mark.asyncio
async def test_dashboard_full_flow(async_client: AsyncClient, test_user_a: dict):
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}
    
    # 1. Add some skills for User A
    await async_client.post("/api/v1/skills", headers=headers, json={"name": "Python", "proficiency": 4})
    await async_client.post("/api/v1/skills", headers=headers, json={"name": "PostgreSQL", "proficiency": 3})
    
    # 2. Submit JDs (this parses and stores matches instantly)
    app1_resp = await async_client.post("/api/v1/applications", headers=headers, json={"job_title": "Role 1", "jd_raw_text": SAMPLE_JD_1})
    app2_resp = await async_client.post("/api/v1/applications", headers=headers, json={"job_title": "Role 2", "jd_raw_text": SAMPLE_JD_2})
    
    assert app1_resp.status_code == 201
    assert app2_resp.status_code == 201
    
    app1_id = app1_resp.json()["id"]
    
    # 3. Test Application List
    list_resp = await async_client.get("/api/v1/dashboard/applications", headers=headers)
    assert list_resp.status_code == 200
    list_data = list_resp.json()["items"]
    assert len(list_data) == 2
    
    # Find app1 in list
    app1_summary = next(app for app in list_data if app["id"] == app1_id)
    # JD1 requires 3 skills. Python, PostgreSQL (matched) -> 2 matched.
    assert app1_summary["required_skills_count"] == 3
    assert app1_summary["matched_skills_count"] == 2
    
    # 4. Test Analytics
    analytics_resp = await async_client.get("/api/v1/dashboard/analytics/skill-gaps", headers=headers)
    assert analytics_resp.status_code == 200
    analytics = analytics_resp.json()
    
    missing_skills = {m["skill_slug"]: m["frequency_count"] for m in analytics["top_missing_skills"]}
    matched_skills = {m["skill_slug"]: m["frequency_count"] for m in analytics["top_matched_skills"]}
    
    # Python is in both JDs and user has it
    assert matched_skills.get("python") == 2
    # Kubernetes is in both JDs and user DOES NOT have it
    assert missing_skills.get("kubernetes") == 2
    
    assert "Kubernetes" in analytics["learning_nudge"]

    # 5. Test Detail Endpoint
    detail_resp = await async_client.get(f"/api/v1/dashboard/applications/{app1_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["application"]["id"] == app1_id
    assert len(detail["application"]["requirements"]) == 3
    assert len(detail["skill_matches"]) == 3
    assert detail["tailored_cv"] is None  # Not tailored yet
    assert detail["interview_prep"] is None


@pytest.mark.asyncio
async def test_tenant_isolation_dashboard(async_client: AsyncClient, test_user_a: dict, test_user_b: dict):
    headers_a = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}
    headers_b = {"Authorization": f"Bearer {test_user_b['tokens'].access_token}"}
    
    # User A submits JD
    app_resp = await async_client.post("/api/v1/applications", headers=headers_a, json={"job_title": "A Role", "jd_raw_text": SAMPLE_JD_1})
    app_id = app_resp.json()["id"]
    
    # User B lists apps - should be empty
    list_b = await async_client.get("/api/v1/dashboard/applications", headers=headers_b)
    assert len(list_b.json()["items"]) == 0
    
    # User B requests User A's app detail
    detail_b = await async_client.get(f"/api/v1/dashboard/applications/{app_id}", headers=headers_b)
    assert detail_b.status_code == 404
    
    # User B requests analytics - should be empty
    analytics_b = await async_client.get("/api/v1/dashboard/analytics/skill-gaps", headers=headers_b)
    assert len(analytics_b.json()["top_missing_skills"]) == 0
