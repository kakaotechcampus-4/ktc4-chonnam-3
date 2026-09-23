"""Authenticated encryption of GitHub tokens at rest."""

import base64
import binascii
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class TokenCipher:
    def __init__(self, base64_key: str) -> None:
        try:
            key = base64.b64decode(base64_key, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("TOKEN_ENCRYPTION_KEY must be base64 encoded") from None
        if len(key) != 32:
            raise ValueError("TOKEN_ENCRYPTION_KEY must contain exactly 32 bytes")
        self._cipher = AESGCM(key)

    def encrypt(self, value: str) -> bytes:
        # 같은 키로 암호화할 때 nonce를 재사용하지 않으며 복호화를 위해 암호문 앞에 저장한다.
        nonce = secrets.token_bytes(12)
        return nonce + self._cipher.encrypt(nonce, value.encode(), None)

    def decrypt(self, value: bytes) -> str:
        try:
            return self._cipher.decrypt(value[:12], value[12:], None).decode()
        except (InvalidTag, ValueError, UnicodeDecodeError):
            raise ValueError("Stored token cannot be decrypted") from None
