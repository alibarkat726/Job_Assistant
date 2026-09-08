import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_learning_crud_and_approval_flow(async_client: AsyncClient, test_user_a: dict):
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}

    # 1. Create a learning entry
    create_resp = await async_client.post(
        "/api/v1/learning",
        headers=headers,
        json={"title": "Test Entry", "content": "I built a new microservice using FastAPI and Docker."}
    )
    assert create_resp.status_code == 201
    entry_id = create_resp.json()["id"]

    # 2. Check pending proposals
    pending_resp = await async_client.get("/api/v1/learning/proposals/pending", headers=headers)
    assert pending_resp.status_code == 200
    proposals = pending_resp.json()
    assert len(proposals) == 1
    
    proposal = proposals[0]
    proposal_id = proposal["id"]
    assert proposal["entry_id"] == entry_id
    assert proposal["is_skill_worthy"] is True
    assert len(proposal["proposed_skills"]) > 0
    
    # 3. Approve proposal partially
    # Approve only the first skill (FastAPI)
    item_to_approve = proposal["proposed_skills"][0]["id"]
    
    approve_resp = await async_client.post(
        f"/api/v1/learning/proposals/{proposal_id}/approve",
        headers=headers,
        json={"approved_item_ids": [item_to_approve]}
    )
    assert approve_resp.status_code == 200
    approved_proposal = approve_resp.json()
    assert approved_proposal["status"] == "approved"
    
    # Ensure one is approved, others are rejected
    for item in approved_proposal["proposed_skills"]:
        if item["id"] == item_to_approve:
            assert item["status"] == "approved"
        else:
            assert item["status"] == "rejected"
            
    # 4. Verify skill was actually created via Module 3 Skills endpoint
    skills_resp = await async_client.get("/api/v1/skills", headers=headers)
    assert skills_resp.status_code == 200
    skills = skills_resp.json()
    assert len(skills) == 1
    assert skills[0]["proficiency"] == 1
    assert skills[0]["source"] == "learning"


@pytest.mark.asyncio
async def test_tenant_isolation_learning(async_client: AsyncClient, test_user_a: dict, test_user_b: dict):
    """User B cannot read or approve User A's learning proposals."""
    headers_a = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}
    headers_b = {"Authorization": f"Bearer {test_user_b['tokens'].access_token}"}

    # User A creates a learning entry
    create_a = await async_client.post(
        "/api/v1/learning", headers=headers_a, json={"content": "I learned Python"}
    )
    assert create_a.status_code == 201
    entry_id_a = create_a.json()["id"]

    # User B cannot see it
    get_b = await async_client.get(f"/api/v1/learning/{entry_id_a}", headers=headers_b)
    assert get_b.status_code == 404

    # User B has no pending proposals
    pending_b = await async_client.get("/api/v1/learning/proposals/pending", headers=headers_b)
    assert pending_b.status_code == 200
    assert len(pending_b.json()) == 0

    # Get User A's proposal ID
    pending_a = await async_client.get("/api/v1/learning/proposals/pending", headers=headers_a)
    proposal_id_a = pending_a.json()[0]["id"]

    # User B cannot approve User A's proposal
    approve_b = await async_client.post(
        f"/api/v1/learning/proposals/{proposal_id_a}/approve",
        headers=headers_b,
        json={"approved_item_ids": []}
    )
    assert approve_b.status_code == 404


@pytest.mark.asyncio
async def test_reject_proposal(async_client: AsyncClient, test_user_a: dict):
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}

    create_resp = await async_client.post(
        "/api/v1/learning",
        headers=headers,
        json={"content": "I built something in React"}
    )
    assert create_resp.status_code == 201

    pending_resp = await async_client.get("/api/v1/learning/proposals/pending", headers=headers)
    proposal_id = pending_resp.json()[0]["id"]

    reject_resp = await async_client.post(
        f"/api/v1/learning/proposals/{proposal_id}/reject",
        headers=headers
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"

    # Verify no skills were created
    skills_resp = await async_client.get("/api/v1/skills", headers=headers)
    assert len(skills_resp.json()) == 0
