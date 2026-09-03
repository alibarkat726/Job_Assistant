from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

# Modern Argon2id hasher configuration
password_hash = PasswordHash((Argon2Hasher(),))


def hash_password(password: str) -> str:
    """Hash password using Argon2id."""
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against Argon2id hash."""
    try:
        return password_hash.verify(plain_password, hashed_password)
    except Exception:
        return False
