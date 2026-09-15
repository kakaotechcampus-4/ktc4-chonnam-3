import base64
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings


class TokenCipher:
    def __init__(self, settings: Settings) -> None:
        self.cipher = AESGCM(
            base64.b64decode(settings.token_encryption_key.get_secret_value(), validate=True)
        )

    def encrypt(self, token: str) -> bytes:
        nonce = secrets.token_bytes(12)
        return nonce + self.cipher.encrypt(nonce, token.encode(), b"devon:github:v1")

    def decrypt(self, encrypted: bytes) -> str:
        return self.cipher.decrypt(encrypted[:12], encrypted[12:], b"devon:github:v1").decode()
