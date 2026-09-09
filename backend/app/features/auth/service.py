"""users upsert + github_accounts upsert. 트랜잭션 경계.
★ 토큰은 core/crypto.py 로 암호화해 BYTEA 에 넣는다. 평문 저장 금지.
★ 연동 직후 initial_sync(M1) 를 enqueue 한다.
★ users.status 가 suspended / withdrawn 이면 로그인을 막는다 (대응 reason 미확정).

확정본 §1 / task-06
"""
