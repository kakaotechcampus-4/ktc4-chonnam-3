"""GitHub 토큰 암복호화 (AES-GCM). access_token_encrypted 는 BYTEA 이고 평문 저장이 금지된다.
키는 TOKEN_ENCRYPTION_KEY (base64 32byte).
쿠키·OAuth state 는 core/security.py 담당 — 섞지 않는다.

확정본 §1 github_accounts / task-06
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

_NONCE_BYTES = 12


class TokenCryptoError(RuntimeError):
    """키 미설정/복호화 실패. 토큰 값 자체는 절대 메시지에 담지 않는다."""


def _key() -> bytes:
    raw = get_settings().token_encryption_key
    if not raw:
        raise TokenCryptoError("TOKEN_ENCRYPTION_KEY is not configured")
    try:
        key = base64.b64decode(raw)
    except (ValueError, TypeError) as exc:  # pragma: no cover - 설정 오류
        raise TokenCryptoError("TOKEN_ENCRYPTION_KEY is not valid base64") from exc
    if len(key) != 32:
        raise TokenCryptoError("TOKEN_ENCRYPTION_KEY must decode to 32 bytes")
    return key


def encrypt_token(plaintext: str) -> bytes:
    """`nonce || ciphertext` 를 BYTEA 로 저장할 형태로 반환한다."""
    nonce = os.urandom(_NONCE_BYTES)
    return nonce + AESGCM(_key()).encrypt(nonce, plaintext.encode("utf-8"), None)


def decrypt_token(blob: bytes) -> str:
    """저장된 BYTEA 를 평문 토큰으로 되돌린다. 호출부는 값을 log 에 남기지 않는다."""
    if len(blob) <= _NONCE_BYTES:
        raise TokenCryptoError("encrypted token is too short")
    nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    try:
        return AESGCM(_key()).decrypt(nonce, ciphertext, None).decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - 원인 노출 금지
        raise TokenCryptoError("failed to decrypt github token") from exc
