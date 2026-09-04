"""
Integration tests for Module 3: Skills & Projects.

These tests exercise the full HTTP API layer (routes → services → repositories),
using the real test database via async_client + db_session fixtures.

Coverage:
  - Full skill CRUD lifecycle
  - Full project CRUD lifecycle
  - Attach/detach skill to/from project (including edge cases)
  - Tenant isolation: User A cannot read/edit/delete User B's skills or projects
  - Cross-tenant attach guard: User A cannot attach User B's skill to their project
"""
import pytest
from httpx import AsyncClient


# ------------------------------------------------------------------ #
# Skills — Full CRUD Lifecycle
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_skill_crud_lifecycle(async_client: AsyncClient, test_user_a: dict):
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}

    # 1. Create skill
    create_resp = await async_client.post(
        "/api/v1/skills",
        headers=headers,
        json={"name": "Python", "proficiency": 4, "category": "language"},
    )
    assert create_resp.status_code == 201
    skill_data = create_resp.json()
    skill_id = skill_data["id"]
    assert skill_data["name"] == "Python"
    assert skill_data["name_slug"] == "python"
    assert skill_data["proficiency"] == 4
    assert skill_data["category"] == "language"
    assert skill_data["source"] == "manual"

    # 2. List skills — should have 1
    list_resp = await async_client.get("/api/v1/skills", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # 3. Get single skill
    get_resp = await async_client.get(f"/api/v1/skills/{skill_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == skill_id

    # 4. Update skill
    update_resp = await async_client.put(
        f"/api/v1/skills/{skill_id}",
        headers=headers,
        json={"proficiency": 5, "category": "backend"},
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["proficiency"] == 5
    assert updated["category"] == "backend"
    assert updated["name"] == "Python"  # name unchanged

    # 5. Delete skill
    delete_resp = await async_client.delete(f"/api/v1/skills/{skill_id}", headers=headers)
    assert delete_resp.status_code == 204

    # 6. Get after delete → 404
    get_after = await async_client.get(f"/api/v1/skills/{skill_id}", headers=headers)
    assert get_after.status_code == 404


@pytest.mark.asyncio
async def test_create_duplicate_skill_case_insensitive_409(
    async_client: AsyncClient, test_user_a: dict
):
    """Creating 'react' and 'React' (same slug) should return 409 on the second attempt."""
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}

    resp1 = await async_client.post("/api/v1/skills", headers=headers, json={"name": "React"})
    assert resp1.status_code == 201

    resp2 = await async_client.post("/api/v1/skills", headers=headers, json={"name": "react"})
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "SKILL_DUPLICATE"


@pytest.mark.asyncio
async def test_get_nonexistent_skill_returns_404(async_client: AsyncClient, test_user_a: dict):
    import uuid
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}
    resp = await async_client.get(f"/api/v1/skills/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404


# ------------------------------------------------------------------ #
# Projects — Full CRUD Lifecycle
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_project_crud_lifecycle(async_client: AsyncClient, test_user_a: dict):
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}

    # 1. Create project with URLs
    create_resp = await async_client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "title": "Job Assistant AI Platform",
            "description": "A multi-tenant AI agent platform.",
            "urls": [
                {"label": "GitHub", "url": "https://github.com/example/job-assistant"},
                {"label": "Live Demo", "url": "https://jobassistant.example.com"},
            ],
            "start_date": "2026-01",
            "is_ongoing": True,
        },
    )
    assert create_resp.status_code == 201
    project_data = create_resp.json()
    project_id = project_data["id"]
    assert project_data["title"] == "Job Assistant AI Platform"
    assert len(project_data["urls"]) == 2
    assert project_data["is_ongoing"] is True
    assert project_data["skills"] == []

    # 2. List projects — should have 1
    list_resp = await async_client.get("/api/v1/projects", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # 3. Get single project
    get_resp = await async_client.get(f"/api/v1/projects/{project_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == project_id

    # 4. Update project
    update_resp = await async_client.put(
        f"/api/v1/projects/{project_id}",
        headers=headers,
        json={"is_ongoing": False, "end_date": "2026-09"},
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["is_ongoing"] is False
    assert updated["end_date"] == "2026-09"
    assert updated["title"] == "Job Assistant AI Platform"  # unchanged

    # 5. Delete project
    delete_resp = await async_client.delete(f"/api/v1/projects/{project_id}", headers=headers)
    assert delete_resp.status_code == 204

    # 6. Get after delete → 404
    get_after = await async_client.get(f"/api/v1/projects/{project_id}", headers=headers)
    assert get_after.status_code == 404


@pytest.mark.asyncio
async def test_project_invalid_url_rejected(async_client: AsyncClient, test_user_a: dict):
    """Non-http(s) URLs must be rejected with 422."""
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}
    resp = await async_client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "title": "Bad URL Project",
            "urls": [{"url": "ftp://invalid.example.com"}],
        },
    )
    assert resp.status_code == 422


# ------------------------------------------------------------------ #
# Skills ↔ Projects — Attach / Detach
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_attach_detach_skill_to_project(async_client: AsyncClient, test_user_a: dict):
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}

    # Create a skill
    skill_resp = await async_client.post(
        "/api/v1/skills", headers=headers, json={"name": "FastAPI", "proficiency": 5}
    )
    assert skill_resp.status_code == 201
    skill_id = skill_resp.json()["id"]

    # Create a project
    project_resp = await async_client.post(
        "/api/v1/projects", headers=headers, json={"title": "API Platform"}
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    # Attach skill to project
    attach_resp = await async_client.post(
        f"/api/v1/projects/{project_id}/skills/{skill_id}", headers=headers
    )
    assert attach_resp.status_code == 200
    project_with_skills = attach_resp.json()
    assert len(project_with_skills["skills"]) == 1
    assert project_with_skills["skills"][0]["name"] == "FastAPI"

    # List project skills
    list_skills_resp = await async_client.get(
        f"/api/v1/projects/{project_id}/skills", headers=headers
    )
    assert list_skills_resp.status_code == 200
    assert len(list_skills_resp.json()) == 1

    # Detach skill from project
    detach_resp = await async_client.delete(
        f"/api/v1/projects/{project_id}/skills/{skill_id}", headers=headers
    )
    assert detach_resp.status_code == 200
    assert detach_resp.json()["skills"] == []


@pytest.mark.asyncio
async def test_attach_skill_duplicate_returns_409(async_client: AsyncClient, test_user_a: dict):
    """Attaching the same skill twice to a project returns 409."""
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}

    skill_id = (
        await async_client.post("/api/v1/skills", headers=headers, json={"name": "Docker"})
    ).json()["id"]
    project_id = (
        await async_client.post("/api/v1/projects", headers=headers, json={"title": "DevOps"})
    ).json()["id"]

    first = await async_client.post(
        f"/api/v1/projects/{project_id}/skills/{skill_id}", headers=headers
    )
    assert first.status_code == 200

    second = await async_client.post(
        f"/api/v1/projects/{project_id}/skills/{skill_id}", headers=headers
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "SKILL_ALREADY_ATTACHED"


@pytest.mark.asyncio
async def test_attach_nonexistent_skill_returns_404(async_client: AsyncClient, test_user_a: dict):
    """Attaching a skill UUID that doesn't exist returns 404."""
    import uuid
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}

    project_id = (
        await async_client.post("/api/v1/projects", headers=headers, json={"title": "Test Project"})
    ).json()["id"]

    resp = await async_client.post(
        f"/api/v1/projects/{project_id}/skills/{uuid.uuid4()}", headers=headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_detach_skill_not_attached_returns_404(async_client: AsyncClient, test_user_a: dict):
    """Detaching a skill that was never attached returns 404."""
    import uuid
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}

    skill_id = (
        await async_client.post("/api/v1/skills", headers=headers, json={"name": "Redis"})
    ).json()["id"]
    project_id = (
        await async_client.post("/api/v1/projects", headers=headers, json={"title": "Cache Project"})
    ).json()["id"]

    resp = await async_client.delete(
        f"/api/v1/projects/{project_id}/skills/{skill_id}", headers=headers
    )
    assert resp.status_code == 404


# ------------------------------------------------------------------ #
# Tenant Isolation — Skills
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_tenant_isolation_skills(
    async_client: AsyncClient, test_user_a: dict, test_user_b: dict
):
    """User B cannot read, update, or delete User A's skills."""
    headers_a = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}
    headers_b = {"Authorization": f"Bearer {test_user_b['tokens'].access_token}"}

    # User A creates a skill
    skill_a_id = (
        await async_client.post(
            "/api/v1/skills", headers=headers_a, json={"name": "Kubernetes"}
        )
    ).json()["id"]

    # User B cannot read User A's skill
    get_b = await async_client.get(f"/api/v1/skills/{skill_a_id}", headers=headers_b)
    assert get_b.status_code == 404

    # User B's skill list is empty
    list_b = await async_client.get("/api/v1/skills", headers=headers_b)
    assert list_b.status_code == 200
    assert len(list_b.json()) == 0

    # User B cannot update User A's skill
    update_b = await async_client.put(
        f"/api/v1/skills/{skill_a_id}", headers=headers_b, json={"proficiency": 1}
    )
    assert update_b.status_code == 404

    # User B cannot delete User A's skill
    delete_b = await async_client.delete(f"/api/v1/skills/{skill_a_id}", headers=headers_b)
    assert delete_b.status_code == 404

    # User A's skill remains intact
    get_a = await async_client.get(f"/api/v1/skills/{skill_a_id}", headers=headers_a)
    assert get_a.status_code == 200
    assert get_a.json()["name"] == "Kubernetes"


# ------------------------------------------------------------------ #
# Tenant Isolation — Projects
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_tenant_isolation_projects(
    async_client: AsyncClient, test_user_a: dict, test_user_b: dict
):
    """User B cannot read, update, or delete User A's projects."""
    headers_a = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}
    headers_b = {"Authorization": f"Bearer {test_user_b['tokens'].access_token}"}

    # User A creates a project
    project_a_id = (
        await async_client.post(
            "/api/v1/projects", headers=headers_a, json={"title": "Secret Project"}
        )
    ).json()["id"]

    # User B cannot read User A's project
    get_b = await async_client.get(f"/api/v1/projects/{project_a_id}", headers=headers_b)
    assert get_b.status_code == 404

    # User B's project list is empty
    list_b = await async_client.get("/api/v1/projects", headers=headers_b)
    assert list_b.status_code == 200
    assert len(list_b.json()) == 0

    # User B cannot update User A's project
    update_b = await async_client.put(
        f"/api/v1/projects/{project_a_id}",
        headers=headers_b,
        json={"title": "Hijacked"},
    )
    assert update_b.status_code == 404

    # User B cannot delete User A's project
    delete_b = await async_client.delete(f"/api/v1/projects/{project_a_id}", headers=headers_b)
    assert delete_b.status_code == 404

    # User A's project remains intact
    get_a = await async_client.get(f"/api/v1/projects/{project_a_id}", headers=headers_a)
    assert get_a.status_code == 200
    assert get_a.json()["title"] == "Secret Project"


# ------------------------------------------------------------------ #
# Tenant Isolation — Cross-Tenant Skill Attach
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_cross_tenant_skill_attach_prevented(
    async_client: AsyncClient, test_user_a: dict, test_user_b: dict
):
    """
    User A cannot attach User B's skill to their own project.
    The skill belongs to B but is invisible to A — returns 404.
    """
    headers_a = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}
    headers_b = {"Authorization": f"Bearer {test_user_b['tokens'].access_token}"}

    # User B creates a skill
    skill_b_id = (
        await async_client.post(
            "/api/v1/skills", headers=headers_b, json={"name": "Terraform"}
        )
    ).json()["id"]

    # User A creates a project
    project_a_id = (
        await async_client.post(
            "/api/v1/projects", headers=headers_a, json={"title": "A's Infrastructure"}
        )
    ).json()["id"]

    # User A tries to attach User B's skill → must be 404 (skill not visible to A)
    resp = await async_client.post(
        f"/api/v1/projects/{project_a_id}/skills/{skill_b_id}", headers=headers_a
    )
    assert resp.status_code == 404
