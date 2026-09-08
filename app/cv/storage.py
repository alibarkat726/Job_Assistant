from abc import ABC, abstractmethod
import os
from pathlib import Path
import uuid
from typing import Tuple
from app.config.settings import settings


class FileStorageService(ABC):
    """Abstract file storage interface for raw CV uploads."""

    @abstractmethod
    async def save_file(self, user_id: uuid.UUID, file_bytes: bytes, original_filename: str) -> str:
        """Save file bytes and return a unique storage key/path."""
        pass

    @abstractmethod
    async def get_file(self, user_id: uuid.UUID, file_key: str) -> bytes:
        """Retrieve stored file bytes by storage key for a user."""
        pass

    @abstractmethod
    async def delete_file(self, user_id: uuid.UUID, file_key: str) -> None:
        """Delete a stored file by key for a user."""
        pass


class LocalStorageService(FileStorageService):
    """
    Local filesystem storage implementation.
    Stores files at `<STORAGE_DIR>/<user_uuid>/<file_uuid>` outside static web roots.
    """

    def __init__(self, base_dir: str = settings.STORAGE_DIR):
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_user_dir(self, user_id: uuid.UUID) -> Path:
        user_dir = (self.base_dir / str(user_id)).resolve()
        # Security check: Ensure user_dir is strictly contained within base_dir
        if not str(user_dir).startswith(str(self.base_dir)):
            raise PermissionError("Access denied: Directory traversal attempt detected.")
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    async def save_file(self, user_id: uuid.UUID, file_bytes: bytes, original_filename: str) -> str:
        user_dir = self._get_user_dir(user_id)
        file_uuid = str(uuid.uuid4())
        ext = Path(original_filename).suffix
        file_key = f"{file_uuid}{ext}" if ext else file_uuid

        target_path = (user_dir / file_key).resolve()
        if not str(target_path).startswith(str(user_dir)):
            raise PermissionError("Access denied: Invalid filename.")

        with open(target_path, "wb") as f:
            f.write(file_bytes)

        return file_key

    async def get_file(self, user_id: uuid.UUID, file_key: str) -> bytes:
        user_dir = self._get_user_dir(user_id)
        target_path = (user_dir / Path(file_key).name).resolve()

        if not str(target_path).startswith(str(user_dir)) or not target_path.is_file():
            raise FileNotFoundError("Requested file does not exist or access is restricted.")

        with open(target_path, "rb") as f:
            return f.read()

    async def delete_file(self, user_id: uuid.UUID, file_key: str) -> None:
        user_dir = self._get_user_dir(user_id)
        target_path = (user_dir / Path(file_key).name).resolve()

        if str(target_path).startswith(str(user_dir)) and target_path.is_file():
            os.remove(target_path)
