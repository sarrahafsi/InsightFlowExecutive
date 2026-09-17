"""
Application-level encryption for secrets stored at rest (OAuth tokens, API keys).

Uses Fernet (AES-128-CBC + HMAC) with a master key kept OUT of the database —
in TOKEN_ENCRYPTION_KEY (.env in dev, a real secret manager in prod). This is
the same envelope-encryption pattern real platforms use: the encrypted blob is
useless without the key, and the key never lives next to the data it protects.
"""
from cryptography.fernet import Fernet, InvalidToken

from core.config import settings


class TokenEncryptionError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = settings.token_encryption_key
    if not key:
        raise TokenEncryptionError(
            "TOKEN_ENCRYPTION_KEY is not set. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" "
            "and add it to .env — without it, connected-app tokens cannot be stored."
        )
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as e:
        raise TokenEncryptionError(f"TOKEN_ENCRYPTION_KEY is not a valid Fernet key: {e}") from e


def encrypt_str(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_str(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:
        raise TokenEncryptionError(
            "Could not decrypt stored value — wrong TOKEN_ENCRYPTION_KEY, or the value "
            "predates encryption being enabled (reconnect the source to fix)."
        ) from e
