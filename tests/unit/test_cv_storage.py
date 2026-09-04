import uuid
import pytest
from app.cv.storage import LocalStorageService


@pytest.mark.asyncio
async def test_local_storage_service(tmp_path):
    storage = LocalStorageService(base_dir=str(tmp_path))
    user_id = uuid.uuid4()
    content = b"Sample CV File Bytes Content"

    # Save file
    file_key = await storage.save_file(user_id, content, "sample_resume.pdf")
    assert file_key.endswith(".pdf")

    # Get file
    retrieved = await storage.get_file(user_id, file_key)
    assert retrieved == content

    # Delete file
    await storage.delete_file(user_id, file_key)

    with pytest.raises(FileNotFoundError):
        await storage.get_file(user_id, file_key)


@pytest.mark.asyncio
async def test_storage_path_traversal_prevention(tmp_path):
    storage = LocalStorageService(base_dir=str(tmp_path))
    user_id = uuid.uuid4()

    with pytest.raises(FileNotFoundError):
        await storage.get_file(user_id, "../../etc/passwd")
