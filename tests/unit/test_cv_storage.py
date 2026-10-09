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


@pytest.mark.asyncio
async def test_storage_rejects_cross_user_symlinks(tmp_path):
    storage = LocalStorageService(str(tmp_path))
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    key = await storage.save_file(user_b, b"private B", "resume.txt")
    (tmp_path / str(user_a)).symlink_to(tmp_path / str(user_b), target_is_directory=True)
    with pytest.raises(PermissionError):
        await storage.get_file(user_a, key)


@pytest.mark.asyncio
async def test_storage_rejects_prefix_sibling_symlink(tmp_path):
    storage = LocalStorageService(str(tmp_path))
    user = uuid.uuid4()
    user_dir = tmp_path / str(user)
    user_dir.mkdir()
    sibling = tmp_path / (str(user) + "-other")
    sibling.mkdir()
    secret = sibling / "secret.txt"
    secret.write_text("private")
    (user_dir / "link.txt").symlink_to(secret)
    with pytest.raises(FileNotFoundError):
        await storage.get_file(user, "link.txt")
