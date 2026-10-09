import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_rag_ingest_and_chat_flow(async_client: AsyncClient, test_user_a: dict):
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}

    # 1. Sync User Vector Data (Ingest all user entities)
    ingest_resp = await async_client.post("/api/v1/chat/ingest/sync-all", headers=headers)
    assert ingest_resp.status_code == 202
    ingest_data = ingest_resp.json()
    assert ingest_data["status"] == "queued"

    # 2. Create Chat Session
    session_resp = await async_client.post(
        "/api/v1/chat/sessions",
        json={"title": "Career & Project Question Session"},
        headers=headers,
    )
    assert session_resp.status_code == 201
    session_data = session_resp.json()
    session_id = session_data["id"]
    assert session_data["title"] == "Career & Project Question Session"

    # 3. List Chat Sessions
    list_resp = await async_client.get("/api/v1/chat/sessions", headers=headers)
    assert list_resp.status_code == 200
    sessions = list_resp.json()
    assert any(s["id"] == session_id for s in sessions)

    # 4. Send Chat Message (RAG Query)
    msg_resp = await async_client.post(
        "/api/v1/chat/messages",
        json={
            "session_id": session_id,
            "content": "What are my main skills and top software engineering projects?",
        },
        headers=headers,
    )
    assert msg_resp.status_code == 200, f"Error: {msg_resp.json()}"
    msg_data = msg_resp.json()
    assert msg_data["role"] == "assistant"
    assert len(msg_data["content"]) > 0

    # 5. Fetch Session Chat Messages
    history_resp = await async_client.get(
        f"/api/v1/chat/sessions/{session_id}/messages",
        headers=headers,
    )
    assert history_resp.status_code == 200
    messages = history_resp.json()
    assert len(messages) >= 2  # 1 user + 1 assistant message


@pytest.mark.asyncio
async def test_rag_tenant_isolation(
    async_client: AsyncClient, test_user_a: dict, test_user_b: dict
):
    """Verify strict tenant isolation: User B cannot view or access User A's chat sessions."""
    user_a_headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}
    user_b_headers = {"Authorization": f"Bearer {test_user_b['tokens'].access_token}"}

    # 1. User A creates a chat session
    session_resp = await async_client.post(
        "/api/v1/chat/sessions",
        json={"title": "User A Private Confidential Session"},
        headers=user_a_headers,
    )
    assert session_resp.status_code == 201
    user_a_session_id = session_resp.json()["id"]

    # 2. User B tries to view User A's session messages -> MUST return 404
    user_b_msg_resp = await async_client.get(
        f"/api/v1/chat/sessions/{user_a_session_id}/messages",
        headers=user_b_headers,
    )
    assert user_b_msg_resp.status_code == 404

    # 3. User B tries to delete User A's session -> MUST return 404
    user_b_del_resp = await async_client.delete(
        f"/api/v1/chat/sessions/{user_a_session_id}",
        headers=user_b_headers,
    )
    assert user_b_del_resp.status_code == 404
