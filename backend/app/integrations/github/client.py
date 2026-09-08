"""GitHub REST v3 — ETag 캐시, rate limit(gh:rl:{githubUserId}). DB 를 모른다.
★ 401 을 받으면 호출부가 github_accounts.token_status='revoked' 로 UPDATE 하고,
  이후 요청은 GitHub 호출 전에 차단한다. token_status 컬럼을 넣은 이유가 이 지점이다.

확정본 §2 error_code / task-08
"""
