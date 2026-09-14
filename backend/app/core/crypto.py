"""GitHub 토큰 암복호화 (AES-GCM). access_token_encrypted / refresh_token_encrypted 는
BYTEA 이고 평문 저장이 금지된다. 키는 TOKEN_ENCRYPTION_KEY.
쿠키·OAuth state 는 core/security.py 담당 — 섞지 않는다.

확정본 §1 github_accounts / task-06
"""
