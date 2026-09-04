import io
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_cv_upload_review_finalize_download_delete(async_client: AsyncClient, test_user_a: dict):
    tokens = test_user_a["tokens"]
    headers = {"Authorization": f"Bearer {tokens.access_token}"}

    # 1. Upload CV file (plain text fallback test)
    sample_cv = b"Jane Doe\njane.doe@example.com | +1-555-0188\nSan Francisco, CA\n\nExperience\nSoftware Engineer - Cloud Inc\nBuilt scalable async microservices in Python.\n\nEducation\nBS Computer Science - Stanford\n\nSkills\nPython, FastAPI, PostgreSQL"
    files = {"file": ("jane_cv.txt", sample_cv, "text/plain")}

    upload_resp = await async_client.post("/api/v1/cvs/upload", headers=headers, files=files)
    assert upload_resp.status_code == 201
    upload_data = upload_resp.json()
    assert upload_data["is_canonical"] is False
    assert upload_data["parsed_data"]["contact_info"]["email"] == "jane.doe@example.com"

    # 2. Get active draft CV profile
    get_resp = await async_client.get("/api/v1/cvs/me", headers=headers)
    assert get_resp.status_code == 200
    cv_profile = get_resp.json()
    assert cv_profile["is_canonical"] is False
    assert cv_profile["email"] == "jane.doe@example.com"

    # 3. Review & Edit draft details
    update_payload = {
        "summary": "Experienced Python Backend Engineer specializing in multi-tenant FastAPI apps.",
        "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "AWS"],
    }
    update_resp = await async_client.put("/api/v1/cvs/draft", headers=headers, json=update_payload)
    assert update_resp.status_code == 200
    updated_profile = update_resp.json()
    assert updated_profile["summary"] == "Experienced Python Backend Engineer specializing in multi-tenant FastAPI apps."
    assert len(updated_profile["skills"]) == 5

    # 4. Finalize draft CV into canonical profile
    finalize_resp = await async_client.post("/api/v1/cvs/finalize", headers=headers)
    assert finalize_resp.status_code == 200
    finalized_profile = finalize_resp.json()
    assert finalized_profile["is_canonical"] is True

    # 5. Download raw uploaded file
    download_resp = await async_client.get("/api/v1/cvs/raw", headers=headers)
    assert download_resp.status_code == 200
    assert download_resp.content == sample_cv

    # 6. Delete CV
    delete_resp = await async_client.delete("/api/v1/cvs/me", headers=headers)
    assert delete_resp.status_code == 204

    # 7. Fetch after deletion returns 404
    get_after_delete = await async_client.get("/api/v1/cvs/me", headers=headers)
    assert get_after_delete.status_code == 404


@pytest.mark.asyncio
async def test_tenant_isolation_cv_intake(
    async_client: AsyncClient, test_user_a: dict, test_user_b: dict
):
    headers_a = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}
    headers_b = {"Authorization": f"Bearer {test_user_b['tokens'].access_token}"}

    # User A uploads CV
    sample_cv = b"User A CV Content\nuser_a@example.com"
    files = {"file": ("user_a_cv.txt", sample_cv, "text/plain")}
    upload_resp = await async_client.post("/api/v1/cvs/upload", headers=headers_a, files=files)
    assert upload_resp.status_code == 201

    # User B tries to fetch User A's CV -> 404 Not Found
    get_b = await async_client.get("/api/v1/cvs/me", headers=headers_b)
    assert get_b.status_code == 404

    # User B tries to download raw file -> 404 Not Found
    download_b = await async_client.get("/api/v1/cvs/raw", headers=headers_b)
    assert download_b.status_code == 404

    # User B tries to update draft -> 404 Not Found
    update_b = await async_client.put("/api/v1/cvs/draft", headers=headers_b, json={"summary": "Hacked"})
    assert update_b.status_code == 404

    # User B tries to delete -> 204 (deletes nothing of User A)
    del_b = await async_client.delete("/api/v1/cvs/me", headers=headers_b)
    assert del_b.status_code == 204

    # User A's CV remains completely intact!
    get_a = await async_client.get("/api/v1/cvs/me", headers=headers_a)
    assert get_a.status_code == 200
    assert get_a.json()["email"] == "user_a@example.com"


@pytest.mark.asyncio
async def test_malformed_file_upload_handling(async_client: AsyncClient, test_user_a: dict):
    headers = {"Authorization": f"Bearer {test_user_a['tokens'].access_token}"}

    # Upload corrupt binary file pretending to be text/pdf
    corrupt_bytes = b"\x00\x01\x02\x03\x04\x05\xff\xfe"
    files = {"file": ("corrupt.bin", corrupt_bytes, "application/octet-stream")}

    upload_resp = await async_client.post("/api/v1/cvs/upload", headers=headers, files=files)
    assert upload_resp.status_code == 400
    err_json = upload_resp.json()
    assert err_json["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
